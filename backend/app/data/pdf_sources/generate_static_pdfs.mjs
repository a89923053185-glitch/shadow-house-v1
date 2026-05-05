import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire("/Users/tanasorokina/Documents/shadow-house-v1/frontend/package.json");
const sharp = require("sharp");

const ROOT = path.resolve("../backend/app/data");
const SOURCE_DIR = path.join(ROOT, "pdf_sources");
const OUT_DIR = path.join(ROOT, "pdfs");

const XML_ESCAPE = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
};

function escapeXml(value) {
  return value.replace(/[&<>"]/g, (char) => XML_ESCAPE[char]);
}

function wrapLine(line, maxChars) {
  if (!line.trim()) return [""];
  const words = line.split(/\s+/);
  const lines = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) lines.push(current);
  return lines;
}

function buildSvg(text) {
  const width = 1224;
  const height = 1584;
  const marginX = 96;
  const paragraphs = text.split(/\n/);
  let y = 120;
  const tspans = [];

  paragraphs.forEach((paragraph, index) => {
    const isTitle = index === 0;
    const isBlank = paragraph.trim() === "";
    if (isBlank) {
      y += 26;
      return;
    }

    const fontSize = isTitle ? 42 : 28;
    const fontWeight = isTitle ? 700 : 400;
    const lineHeight = isTitle ? 52 : 39;
    const maxChars = isTitle ? 38 : 68;
    for (const line of wrapLine(paragraph, maxChars)) {
      tspans.push(
        `<text x="${marginX}" y="${y}" font-family="Arial, Helvetica, sans-serif" font-size="${fontSize}" font-weight="${fontWeight}" fill="#2f1d12">${escapeXml(line)}</text>`
      );
      y += lineHeight;
    }
  });

  return `
<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#fff7ef"/>
  <rect x="52" y="52" width="${width - 104}" height="${height - 104}" rx="28" fill="#ffffff" stroke="#d9a26a" stroke-width="3"/>
  ${tspans.join("\n  ")}
</svg>`;
}

function pdfWithJpeg(jpeg, width, height) {
  const imageObj = Buffer.concat([
    Buffer.from(`5 0 obj\n<< /Type /XObject /Subtype /Image /Width ${width} /Height ${height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`, "binary"),
    jpeg,
    Buffer.from("\nendstream\nendobj\n", "binary"),
  ]);
  const objects = [
    Buffer.from("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n", "binary"),
    Buffer.from("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n", "binary"),
    Buffer.from("3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n", "binary"),
    Buffer.from("4 0 obj\n<< /Length 35 >>\nstream\nq\n612 0 0 792 0 0 cm\n/Im1 Do\nQ\nendstream\nendobj\n", "binary"),
    imageObj,
  ];

  const chunks = [Buffer.from("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n", "binary")];
  const offsets = [0];
  for (const obj of objects) {
    offsets.push(Buffer.concat(chunks).length);
    chunks.push(obj);
  }

  const body = Buffer.concat(chunks);
  const xrefOffset = body.length;
  const xref = [
    `xref\n0 ${objects.length + 1}\n`,
    "0000000000 65535 f \n",
    ...offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`),
    `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`,
  ].join("");

  return Buffer.concat([body, Buffer.from(xref, "binary")]);
}

async function generate(name) {
  const text = await fs.readFile(path.join(SOURCE_DIR, `${name}.txt`), "utf8");
  const svg = buildSvg(text);
  const jpeg = await sharp(Buffer.from(svg)).jpeg({ quality: 94 }).toBuffer();
  const pdf = pdfWithJpeg(jpeg, 1224, 1584);
  await fs.writeFile(path.join(OUT_DIR, `${name}.pdf`), pdf);
}

await fs.mkdir(OUT_DIR, { recursive: true });
await generate("blueprint_sample");
await generate("shadow_tools");
