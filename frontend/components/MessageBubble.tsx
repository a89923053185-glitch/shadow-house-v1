import { Message } from "@/lib/types";
import type { ReactNode } from "react";

type Props = {
  message: Message;
};

function quoteForScreen(text: string) {
  const trimmed = text.trim();
  if (!trimmed) return trimmed;
  if (trimmed.startsWith("«") && trimmed.endsWith("»")) return trimmed;
  return `«${trimmed.replace(/^["«]|["»]$/g, "")}»`;
}

const STRONG_PHRASES = [
  "Главный способ торможения:",
  "Главная внутренняя причина:",
  "Это проявляется так:",
  "Что происходит внутри:",
  "Где это проявляется сильнее всего:",
  "Но цена этой защиты уже становится заметной:",
  "Формула механизма",
  "Архитектура",
  "Твой скрытый ресурс",
  "Фраза, которую можно сохранить",
  "Микро-разрешение",
];

const SECTION_LABELS = [
  "Ключевая тень",
  "Ключевые тени",
  "Формула механизма",
  "Архитектура",
  "Что происходит внутри",
  "Где это проявляется сильнее всего",
  "Скорее всего, этот механизм защищает тебя от",
  "Но цена этой защиты уже становится заметной",
  "Твой скрытый ресурс",
  "Фраза, которую можно сохранить",
  "Микро-разрешение",
  "Как это проявляется",
  "Цена",
  "Объяснение без стыда",
  "Скрытый ресурс",
  "Фраза для скрина",
];

const SECTION_LABEL_PATTERN = SECTION_LABELS.map((label) => label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");

function renderInlineStrong(text: string): ReactNode {
  const escaped = STRONG_PHRASES.map((phrase) => phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "g");
  return text.split(pattern).map((part, index) =>
    STRONG_PHRASES.includes(part) ? <strong key={index}>{part}</strong> : part
  );
}

function renderParagraph(paragraph: string, index: number, keyPrefix = "paragraph") {
  if (paragraph === "Паспорт тени") {
    return <div key={`${keyPrefix}-${index}`} className="bubblePassportTitle">{paragraph}</div>;
  }

  if (paragraph === "«Чертеж дома»") {
    return <div key={`${keyPrefix}-${index}`} className="bubbleOfferTitle">{paragraph}</div>;
  }

  const shadowTitleMatch = paragraph.match(/^Твоя главная тень сейчас — (.+)\.$/);
  if (shadowTitleMatch) {
    return (
      <div key={`${keyPrefix}-${index}`} className="bubbleMainShadowTitle">
        <span className="bubbleMainShadowIntro">Твоя главная тень сейчас —</span>
        <span className="bubbleMainShadowName">{shadowTitleMatch[1]}</span>
      </div>
    );
  }

  const lines = paragraph
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const firstLine = lines[0] || "";
  const labelMatch = firstLine.match(new RegExp(`^(${SECTION_LABEL_PATTERN}):\\s*(.*)$`));

  if (labelMatch) {
    const label = labelMatch[1];
    const leadingValue = labelMatch[2] || "";
    const bodyLines = [leadingValue, ...lines.slice(1)].map((line) => line.trim()).filter(Boolean);
    const value = label === "Фраза для скрина" ? quoteForScreen(bodyLines.join(" ")) : bodyLines.join(" ");
    return (
      <div key={`${keyPrefix}-${index}`} className="bubbleSectionBlock">
        <div className="bubbleSectionLabel">{label}:</div>
        <div className="bubbleSectionValue">{renderInlineStrong(value)}</div>
      </div>
    );
  }

  const bulletItems = lines
    .filter((line) => line.startsWith("•"))
    .map((line) => line.replace(/^•\s*/, "").replace(/;$/, "").trim());
  const introLines = lines.filter((line) => !line.startsWith("•"));

  if (bulletItems.length) {
    return (
      <div key={`${keyPrefix}-${index}`} className="bubbleStructuredBlock">
        {introLines.length ? <p className="bubbleParagraph">{renderInlineStrong(introLines.join(" "))}</p> : null}
        <ul className="bubbleBulletList">
          {bulletItems.map((item, itemIndex) => (
            <li key={`${keyPrefix}-${index}-${itemIndex}`}>{renderInlineStrong(item)}</li>
          ))}
        </ul>
      </div>
    );
  }

  if (paragraph === "Выбери вариант ниже.") {
    return <p key={`${keyPrefix}-${index}`} className="bubbleStepHint">{paragraph}</p>;
  }

  if (paragraph === "Персональная карта с личным проектом твоего ДОМА.") {
    return (
      <div key={`${keyPrefix}-${index}`} className="bubbleParagraphWithAction">
        <p className="bubbleParagraph">{renderInlineStrong(paragraph)}</p>
        <a className="blueprintDetailsButton" href="/downloads/blueprint-offer.pdf" target="_blank" rel="noreferrer">
          Подробно про чертеж
        </a>
      </div>
    );
  }

  if (paragraph.startsWith("Вопрос на вырост:")) {
    return <p key={`${keyPrefix}-${index}`} className="bubbleGrowthQuestion">{renderInlineStrong(paragraph)}</p>;
  }

  return <p key={`${keyPrefix}-${index}`} className="bubbleParagraph">{renderInlineStrong(paragraph)}</p>;
}

function mergeDetachedSectionValues(paragraphs: string[]) {
  const merged: string[] = [];

  for (let index = 0; index < paragraphs.length; index += 1) {
    const paragraph = paragraphs[index];
    const isEmptySectionLabel = new RegExp(`^(${SECTION_LABEL_PATTERN}):\\s*$`).test(paragraph);

    if (isEmptySectionLabel && paragraphs[index + 1]) {
      merged.push(`${paragraph}\n${paragraphs[index + 1]}`);
      index += 1;
    } else {
      merged.push(paragraph);
    }
  }

  return merged;
}

function renderAssistantText(text: string) {
  const paragraphs = text
    .split("\n\n")
    .map((part) => part.trim())
    .filter(Boolean);

  const separatorIndex = paragraphs.indexOf("---");
  if (separatorIndex >= 0) {
    const beforeOffer = mergeDetachedSectionValues(paragraphs.slice(0, separatorIndex));
    const offer = paragraphs.slice(separatorIndex + 1);
    return (
      <>
        <div className="bubblePassportContent">
          {beforeOffer.map((paragraph, index) => renderParagraph(paragraph, index, "passport"))}
        </div>
        <div className="bubbleFinalBlock">
          {offer.map((paragraph, index) => renderParagraph(paragraph, index, "offer"))}
        </div>
        <div className="checklistGiftBlock">
          <div className="checklistGiftTitle">Подарок после диагностики</div>
          <p className="checklistGiftText">
            Ты уже увидел(а) свой механизм. Чтобы не бороться с ним в лоб, забери короткий чек-лист: 5 шагов,
            чтобы обойти свою Тень.
          </p>
          <a className="checklistGiftButton" href="/downloads/checklist-shadow.pdf" target="_blank" rel="noreferrer">
            Забрать чек-лист
          </a>
        </div>
      </>
    );
  }

  return paragraphs.map((paragraph, index) => renderParagraph(paragraph, index));
}

export function MessageBubble({ message }: Props) {
  const rowClass = message.role === "user" ? "bubbleRow bubbleRowUser" : "bubbleRow bubbleRowAssistant";
  const bubbleClass = message.role === "user" ? "bubble bubbleUser" : "bubble bubbleAssistant";
  const roleLabel = message.role === "assistant" ? "КЭТ" : "Вы";

  return (
    <div className={rowClass}>
      <div className={bubbleClass}>
        <div className="bubbleRole">{roleLabel}</div>
        <div className="bubbleText">
          {message.role === "assistant" ? renderAssistantText(message.text) : message.text}
        </div>
      </div>
    </div>
  );
}
