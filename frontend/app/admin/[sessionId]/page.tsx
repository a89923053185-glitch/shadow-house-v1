"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { getAdminResultPrintUrl, getAdminSessionDetail } from "@/lib/api";
import { AdminSessionDetail } from "@/lib/types";

const FINAL_BLUEPRINT_TEXT =
  "Сейчас ты увидел(а) важную вещь.\nНе «проблему». А механизм.\nИ он уже не будет развидеться.\n\nДальше можно разобрать не только «где ломается», а всю конструкцию: где ты сейчас, куда на самом деле хочешь, на что можешь опереться и как из этого собирается путь.\n\nЭто и есть:\n«Чертеж дома»\n\nПерсональная карта с личным проектом твоего ДОМА.";

function formatDate(value?: string | null) {
  if (!value) return "нет данных";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function renderValue(value?: unknown) {
  return typeof value === "string" && value.trim() ? value : "нет данных";
}

function renderNumber(value?: number | null) {
  return typeof value === "number" ? String(value) : "нет данных";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function textFrom(value: unknown) {
  if (value === null || value === undefined || value === "") return "нет данных";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return "нет данных";
}

function passportFrom(detail: AdminSessionDetail) {
  return asRecord(asRecord(detail.v1_2).passport);
}

function finalLinkFrom(detail: AdminSessionDetail) {
  return asRecord(asRecord(detail.v1_2).final_link);
}

function resultText(detail: AdminSessionDetail, passport: Record<string, unknown>, field: string, fallback?: unknown) {
  return textFrom(passport[field] || fallback);
}

function buildResultRows(detail: AdminSessionDetail) {
  const passport = passportFrom(detail);
  const finalLink = finalLinkFrom(detail);
  const mainShadow = resultText(detail, passport, "title", detail.top_shadow_names[0]);

  return [
    ["Паспорт тени", renderValue(detail.client_text)],
    ["Твоя главная тень сейчас", mainShadow],
    ["Итоговая тень", mainShadow],
    ["Вторая тень", textFrom(finalLink.personality_shadow_name)],
    ["Формула механизма", resultText(detail, passport, "formula_mechanism", detail.mechanism_formula)],
    ["Архитектура", resultText(detail, passport, "architecture")],
    ["Что происходит внутри", resultText(detail, passport, "inner_mechanism", detail.manifestation)],
    ["Где это проявляется сильнее всего", resultText(detail, passport, "main_sphere")],
    ["От чего защищает", resultText(detail, passport, "main_protection")],
    ["Цена защиты", resultText(detail, passport, "main_price", detail.price)],
    ["Твой скрытый ресурс", resultText(detail, passport, "hidden_resource", detail.hidden_resource)],
    ["Фраза, которую можно сохранить", resultText(detail, passport, "save_phrase", detail.screen_phrase)],
    ["Микро-разрешение", resultText(detail, passport, "micro_permission", detail.micro_permission)],
    ["Вопрос на вырост", renderValue(detail.result_summary)],
    ["Финальный текст про Чертеж дома", FINAL_BLUEPRINT_TEXT],
  ];
}

export default function AdminSessionPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params?.sessionId || "";
  const [detail, setDetail] = useState<AdminSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      if (!sessionId) return;
      try {
        setLoading(true);
        setError(null);
        const response = await getAdminSessionDetail(sessionId);
        if (active) {
          setDetail(response);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Не удалось загрузить запись.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      active = false;
    };
  }, [sessionId]);

  const resultRows = useMemo(() => detail ? buildResultRows(detail) : [], [detail]);

  return (
    <main className="adminPage">
      <div className="adminShell">
        <header className="adminHero adminHeroCompact">
          <div>
            <div className="adminEyebrow">Карточка клиента</div>
            <h1>{detail?.display_name || "Клиент"}</h1>
          </div>
          <Link href="/admin" className="adminBackLink">← К списку</Link>
        </header>

        {loading ? <div className="adminState">Загружаю данные…</div> : null}
        {error ? <div className="adminState adminStateError">{error}</div> : null}

        {!loading && !error && detail ? (
          <div className="adminDetailGrid">
            <section className="adminCard adminCardWide">
              <div className="adminPanelHeader">
                <div className="adminCardTitle">Основное</div>
                <a href={getAdminResultPrintUrl(detail.session_id)} target="_blank" rel="noreferrer" className="adminExportButton">
                  Печатная версия результата
                </a>
              </div>
              <dl className="adminPrimaryGrid">
                <div><dt>session_id</dt><dd>{detail.session_id}</dd></div>
                <div><dt>Имя</dt><dd>{renderValue(detail.display_name)}</dd></div>
                <div><dt>Возраст</dt><dd>{renderNumber(detail.user_age)}</dd></div>
                <div><dt>Телефон</dt><dd>{renderValue(detail.phone_number)}</dd></div>
                <div><dt>Подтвержден ли номер</dt><dd>{detail.phone_verified ? "Да" : "Нет"}</dd></div>
                <div><dt>Скачивал бонусный файл</dt><dd>{detail.bonus_downloaded ? "Да" : "Нет"}</dd></div>
                <div><dt>Скачивал чертеж</dt><dd>{detail.blueprint_downloaded ? "Да" : "Нет"}</dd></div>
                <div><dt>Дата старта</dt><dd>{formatDate(detail.created_at)}</dd></div>
                <div><dt>Последняя активность</dt><dd>{formatDate(detail.last_activity_at)}</dd></div>
                <div><dt>Статус прохождения</dt><dd>{detail.status_label}</dd></div>
                <div><dt>Где остановился</dt><dd>{detail.stopped_at_label}</dd></div>
                <div><dt>Желаемая жизнь</dt><dd>{renderValue(detail.user_goal_text || detail.dream)}</dd></div>
              </dl>
            </section>

            <section className="adminCard adminCardWide">
              <div className="adminCardTitle">Паспорт тени</div>
              <dl className="adminDetailList adminResultList">
                {resultRows.map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          </div>
        ) : null}
      </div>
    </main>
  );
}
