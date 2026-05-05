import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Тень дома",
  description: "КЭТ проводит вводную диагностику скрытой трещины в системе Дом"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
