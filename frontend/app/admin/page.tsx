"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getAdminExportUrl, getAdminSessions } from "@/lib/api";
import { AdminPeriod, AdminSessionSummary } from "@/lib/types";

const PERIODS: Array<{ key: AdminPeriod; label: string }> = [
  { key: "today", label: "Сегодня" },
  { key: "7d", label: "7 дней" },
  { key: "30d", label: "30 дней" },
];

function formatDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value)).replace(",", "");
}

function finalShadow(item: AdminSessionSummary) {
  return item.passport_title || item.top_shadow_names[0] || item.behavior_shadow_name || "—";
}

function AdminCell({ value }: { value?: string | number | null }) {
  const text = value === undefined || value === null || value === "" ? "—" : String(value);
  return <span className="adminCellText" title={text}>{text}</span>;
}

export default function AdminPage() {
  const [period, setPeriod] = useState<AdminPeriod>("30d");
  const [customStartDraft, setCustomStartDraft] = useState("");
  const [customEndDraft, setCustomEndDraft] = useState("");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<AdminSessionSummary[]>([]);
  const [analytics, setAnalytics] = useState<NonNullable<Awaited<ReturnType<typeof getAdminSessions>>["analytics"]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const response = await getAdminSessions({
          filter: "all",
          period,
          search,
          startDate: period === "custom" ? customStart : undefined,
          endDate: period === "custom" ? customEnd : undefined,
        });
        if (active) {
          setItems(response.items);
          setAnalytics(response.analytics || {});
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Не удалось загрузить список.");
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
  }, [period, search, customStart, customEnd]);

  const visibleItems = useMemo(() => items, [items]);
  const completedSessions = analytics.completed_sessions ?? 0;
  const reachedPassport = analytics.reached_passport ?? completedSessions;
  const exportQuery = useMemo(
    () => ({
      filter: "all" as const,
      period,
      search,
      startDate: period === "custom" ? customStart : undefined,
      endDate: period === "custom" ? customEnd : undefined,
    }),
    [period, search, customStart, customEnd]
  );

  return (
    <main className="adminPage">
      <div className="adminShell">
        <header className="adminHero">
          <div className="adminEyebrow">Внутренний экран</div>
          <h1>Прохождения «Тени дома»</h1>
          <p>Рабочий список сессий: кто начал, где остановился и какой результат уже собран.</p>
        </header>

        <section className="adminMetricsGrid">
          <div className="adminMetricCard">
            <span>Всего сессий</span>
            <strong>{analytics.total_sessions ?? items.length}</strong>
          </div>
          <div className="adminMetricCard">
            <span>Завершено</span>
            <strong>{completedSessions}</strong>
          </div>
          <div className="adminMetricCard">
            <span>Дошли до паспорта</span>
            <strong>{reachedPassport}</strong>
          </div>
          <div className="adminMetricCard">
            <span>Конверсия в паспорт</span>
            <strong>{analytics.passport_conversion_percent ?? 0}%</strong>
          </div>
        </section>

        <section className="adminToolbar">
          <div className="adminToolbarBlock">
            <div className="adminToolbarLabel">Период</div>
            <div className="adminFilterRow">
              {PERIODS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`adminFilterButton${period === item.key ? " isActive" : ""}`}
                  onClick={() => {
                    setPeriod(item.key);
                    setCustomStart("");
                    setCustomEnd("");
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="adminToolbarBlock adminToolbarDates">
            <div className="adminToolbarLabel">Свой период</div>
            <div className="adminDateRange">
              <label>
                <span>с</span>
                <input type="date" value={customStartDraft} onChange={(event) => setCustomStartDraft(event.target.value)} />
              </label>
              <label>
                <span>по</span>
                <input type="date" value={customEndDraft} onChange={(event) => setCustomEndDraft(event.target.value)} />
              </label>
              <button
                type="button"
                className={`adminFilterButton${period === "custom" ? " isActive" : ""}`}
                onClick={() => {
                  setCustomStart(customStartDraft);
                  setCustomEnd(customEndDraft);
                  setPeriod("custom");
                }}
              >
                Применить
              </button>
            </div>
          </div>

          <div className="adminToolbarBlock adminToolbarSearch">
            <div className="adminToolbarLabel">Поиск</div>
            <input
              className="adminSearchInput"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Имя или телефон"
            />
          </div>

          <div className="adminExportRow">
            <a href={getAdminExportUrl("xlsx", exportQuery)} className="adminExportButton">
              Выгрузить Excel
            </a>
          </div>
        </section>

        <section className="adminPanel">
          <div className="adminPanelHeader">
            <div>
              <div className="adminPanelTitle">Список прохождений</div>
              <div className="adminPanelMeta">Найдено: {visibleItems.length}</div>
            </div>
          </div>

          {loading ? <div className="adminState">Загружаю данные…</div> : null}
          {error ? <div className="adminState adminStateError">{error}</div> : null}

          {!loading && !error ? (
            <div className="adminTableWrap">
              <table className="adminTable">
                <thead>
                  <tr>
                    <th>Дата старта</th>
                    <th>Последняя активность</th>
                    <th>Имя</th>
                    <th>Возраст</th>
                    <th>Телефон</th>
                    <th>Подтверждение номера</th>
                    <th>Скачивал бонусный файл</th>
                    <th>Скачивал чертеж</th>
                    <th>Статус прохождения</th>
                    <th>Где остановился</th>
                    <th>Желаемая жизнь</th>
                    <th>Итоговая тень</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {visibleItems.map((item) => (
                    <tr key={item.session_id}>
                      <td><AdminCell value={formatDate(item.created_at)} /></td>
                      <td><AdminCell value={formatDate(item.last_activity_at)} /></td>
                      <td><AdminCell value={item.display_name} /></td>
                      <td><AdminCell value={item.user_age} /></td>
                      <td><AdminCell value={item.phone_number} /></td>
                      <td><AdminCell value={item.phone_verified ? "Да" : "Нет"} /></td>
                      <td><AdminCell value={item.bonus_downloaded ? "Да" : "Нет"} /></td>
                      <td><AdminCell value={item.blueprint_downloaded ? "Да" : "Нет"} /></td>
                      <td><AdminCell value={item.status_label} /></td>
                      <td><AdminCell value={item.stopped_at_label} /></td>
                      <td><AdminCell value={item.dream} /></td>
                      <td><AdminCell value={finalShadow(item)} /></td>
                      <td>
                        <Link href={`/admin/${item.session_id}`} className="adminDetailLink">
                          Открыть
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
