"use client";

import { MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import { ChoiceButtons } from "@/components/ChoiceButtons";
import { ContactGateCard } from "@/components/ContactGateCard";
import { MessageBubble } from "@/components/MessageBubble";
import { ProgressBar } from "@/components/ProgressBar";
import { formatRussianPhone, validateRussianPhone } from "@/lib/phone";
import { createSession, recordBlueprintOpen, recordBonusDownload, requestPhoneCode, resetSession, sendMessage, verifyPhoneCode } from "@/lib/api";
import { ApiResponse, Message } from "@/lib/types";

const LOCKED_RESULT_MARKERS = [
  "### Паспорт тени",
  "Паспорт тени готов",
  "Ключевая тень:",
  "Ключевые тени:",
  "Формула механизма:",
  "Чертеж дома",
];

const CONTACT_GATE_LOCKED_MESSAGE =
  "Результат готов.";

function assistantMessageToPlainText(text: string) {
  return text.replace(/\*\*/g, "").replace(/###/g, "").trim();
}

function hasLockedResultLeak(text: string) {
  return LOCKED_RESULT_MARKERS.some((marker) => text.includes(marker));
}

function sanitizeAssistantMessage(response: ApiResponse) {
  if (response.meta?.result_unlocked === true) {
    return response.assistant_message;
  }

  if (response.meta?.result_ready === true || response.meta?.final_offer === true || response.meta?.passport) {
    return response.assistant_message;
  }

  if (response.input_mode === "contact") {
    return response.assistant_message || CONTACT_GATE_LOCKED_MESSAGE;
  }

  if (hasLockedResultLeak(response.assistant_message)) {
    return CONTACT_GATE_LOCKED_MESSAGE;
  }

  return response.assistant_message;
}

function splitAssistantMessage(text: string, inputMode: ApiResponse["input_mode"]) {
  const chunks: string[] = [];
  const shadowSeparator = "\n\n**Тень ";

  if (text.includes(shadowSeparator)) {
    const [beforeShadow, shadowPart] = text.split(shadowSeparator, 2);
    if (beforeShadow.trim()) {
      chunks.push(beforeShadow.trim());
    }
    if (shadowPart.trim()) {
      chunks.push(`**Тень ${shadowPart.trim()}`);
    }
  } else {
    chunks.push(text.trim());
  }

  const normalized: string[] = [];
  for (const chunk of chunks) {
    const parts = chunk.split("\n\n");
    const lastPart = parts[parts.length - 1]?.trim() || "";
    const leading = parts.slice(0, -1).join("\n\n").trim();

    if (leading && lastPart.endsWith("?")) {
      normalized.push(leading, lastPart);
      continue;
    }

    normalized.push(chunk.trim());
  }

  return normalized.filter(Boolean).map(assistantMessageToPlainText);
}

function assistantMessagesFromResponse(response: ApiResponse): Message[] {
  return splitAssistantMessage(sanitizeAssistantMessage(response), response.input_mode).map((text) => ({
    id: crypto.randomUUID(),
    role: "assistant" as const,
    text,
  }));
}

function clearStoredAccessTokens() {
  if (typeof window === "undefined") return;

  const prefix = "shadow-house-access:";
  const keysToRemove: string[] = [];
  for (let index = 0; index < window.sessionStorage.length; index += 1) {
    const key = window.sessionStorage.key(index);
    if (key?.startsWith(prefix)) {
      keysToRemove.push(key);
    }
  }

  for (const key of keysToRemove) {
    window.sessionStorage.removeItem(key);
  }
}

function isInteractiveStep(response: ApiResponse | null) {
  if (!response) return false;
  return response.input_mode === "text" || response.input_mode === "choices" || response.input_mode === "contact";
}

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

const MOBILE_SECTION_LABELS = [
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

const MOBILE_SECTION_LABEL_PATTERN = MOBILE_SECTION_LABELS.map((label) => label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");

function renderInlineStrong(text: string) {
  const escaped = STRONG_PHRASES.map((phrase) => phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "g");
  return text.split(pattern).map((part, index) =>
    STRONG_PHRASES.includes(part) ? <strong key={index}>{part}</strong> : part
  );
}

function cleanMobileSection(section: string, hideShadowHeading: boolean) {
  let text = section.trim();
  if (hideShadowHeading) {
    text = text.replace(/^Тень(?:\s+\d+)?\.\s+[^\n]+\.?\s*/i, "").trim();
  }
  return text;
}

function mergeDetachedMobileSectionValues(paragraphs: string[]) {
  const merged: string[] = [];

  for (let index = 0; index < paragraphs.length; index += 1) {
    const paragraph = paragraphs[index];
    const isEmptySectionLabel = new RegExp(`^(${MOBILE_SECTION_LABEL_PATTERN}):\\s*$`).test(paragraph);

    if (isEmptySectionLabel && paragraphs[index + 1]) {
      merged.push(`${paragraph}\n${paragraphs[index + 1]}`);
      index += 1;
    } else {
      merged.push(paragraph);
    }
  }

  return merged;
}

function renderStructuredSection(section: string, keyPrefix: string, options?: { hideShadowHeading?: boolean; resultMode?: boolean }) {
  const cleanedSection = cleanMobileSection(section, Boolean(options?.hideShadowHeading));
  if (!cleanedSection) return null;

  const paragraphs = mergeDetachedMobileSectionValues(cleanedSection
    .split("\n\n")
    .map((part) => part.trim())
    .filter(Boolean));

  const renderMobileParagraph = (paragraph: string, index: number, scopedKeyPrefix = keyPrefix) => {
    if (paragraph === "Паспорт тени") {
      if (options?.resultMode) {
        return null;
      }
      return <div key={`${scopedKeyPrefix}-${index}`} className="mobileSectionTitle">{paragraph}</div>;
    }

  if (paragraph === "«Чертеж дома»") {
    return <div key={`${scopedKeyPrefix}-${index}`} className="mobileOfferTitle">{paragraph}</div>;
  }

    const shadowTitleMatch = paragraph.match(/^Твоя главная тень сейчас — (.+)\.$/);
    if (shadowTitleMatch) {
      return (
        <div key={`${scopedKeyPrefix}-${index}`} className="mobileMainShadowTitle">
          Твоя главная тень сейчас — <span>{shadowTitleMatch[1]}</span>.
        </div>
      );
    }

    const lines = paragraph
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    const firstLine = lines[0] || "";
    const labelMatch = firstLine.match(new RegExp(`^(${MOBILE_SECTION_LABEL_PATTERN}):\\s*(.*)$`));

    if (labelMatch) {
      const label = labelMatch[1];
      const leadingValue = labelMatch[2] || "";
      const bodyLines = [leadingValue, ...lines.slice(1)].map((line) => line.trim()).filter(Boolean);
      const value = label === "Фраза для скрина" ? quoteForScreen(bodyLines.join(" ")) : bodyLines.join(" ");
      return (
        <div key={`${scopedKeyPrefix}-${index}`} className="mobileSectionBlock">
          <div className="mobileSectionLabel">{label}:</div>
          <div className="mobileSectionValue">{renderInlineStrong(value)}</div>
        </div>
      );
    }

    const bulletItems = lines
      .filter((line) => line.startsWith("•"))
      .map((line) => line.replace(/^•\s*/, "").replace(/;$/, "").trim());
    const introLines = lines.filter((line) => !line.startsWith("•"));

    if (bulletItems.length) {
      return (
        <div key={`${scopedKeyPrefix}-${index}`} className="mobileStructuredBlock">
          {introLines.length ? <p>{renderInlineStrong(introLines.join(" "))}</p> : null}
          <ul className="mobileBulletList">
            {bulletItems.map((item, itemIndex) => (
              <li key={`${scopedKeyPrefix}-${index}-${itemIndex}`}>{renderInlineStrong(item)}</li>
            ))}
          </ul>
        </div>
      );
    }

    if (paragraph === "Выбери вариант ниже.") {
      return <p key={`${scopedKeyPrefix}-${index}`} className="mobileStepHint">{paragraph}</p>;
    }

    if (lines[0] === "Например:" && lines.some((line) => line.startsWith("—"))) {
      const exampleLines = lines.slice(1).filter((line) => line.startsWith("—")).flatMap((line) => {
        const normalized = line.replace(/^—\s*/, "").trim();
        if (normalized.includes("свой ритм, больше здоровья")) {
          return [
            normalized.replace(/,\s*больше здоровья.*$/, ""),
            "больше здоровья и внутренней гармонии",
          ];
        }
        return [normalized];
      });
      const noteLines = lines.slice(1).filter((line) => !line.startsWith("—"));

      return (
        <div key={`${scopedKeyPrefix}-${index}`} className="mobileExamplesBlock">
          <p>Например:</p>
          <ul>
            {exampleLines.map((line, lineIndex) => (
              <li key={`${scopedKeyPrefix}-${index}-${lineIndex}`}>{renderInlineStrong(line)}</li>
            ))}
          </ul>
          {noteLines.map((line, lineIndex) => (
            <p key={`${scopedKeyPrefix}-${index}-note-${lineIndex}`}>{renderInlineStrong(line)}</p>
          ))}
        </div>
      );
    }

    if (paragraph === "Персональная карта с личным проектом твоего ДОМА.") {
      return (
        <div key={`${scopedKeyPrefix}-${index}`} className="mobileParagraphWithAction">
          <p className={options?.resultMode ? "mobileResultParagraph" : undefined}>{renderInlineStrong(paragraph)}</p>
          <a className="blueprintDetailsButton" href="/downloads/blueprint-offer.pdf" target="_blank" rel="noreferrer">
            Подробно про чертеж
          </a>
        </div>
      );
    }

    return <p key={`${scopedKeyPrefix}-${index}`} className={options?.resultMode ? "mobileResultParagraph" : undefined}>{renderInlineStrong(paragraph)}</p>;
  };

  const separatorIndex = paragraphs.indexOf("---");
  if (separatorIndex >= 0) {
    const beforeOffer = paragraphs.slice(0, separatorIndex);
    const offer = paragraphs.slice(separatorIndex + 1);
    return (
      <>
        {beforeOffer.map((paragraph, index) => renderMobileParagraph(paragraph, index, `${keyPrefix}-passport`))}
        <div className="mobileOfferBlock">
          {offer.map((paragraph, index) => renderMobileParagraph(paragraph, index, `${keyPrefix}-offer`))}
        </div>
        <div className="checklistGiftBlock mobileChecklistGiftBlock">
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

  return paragraphs.map((paragraph, index) => renderMobileParagraph(paragraph, index));
}

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [apiState, setApiState] = useState<ApiResponse | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [codeRequested, setCodeRequested] = useState(false);
  const [devCode, setDevCode] = useState<string | null>(null);
  const [resultAccessToken, setResultAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [verifyingCode, setVerifyingCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isMobileFlow, setIsMobileFlow] = useState(false);
  const [mobileFlowStarted, setMobileFlowStarted] = useState(false);
  const [initStarted, setInitStarted] = useState(false);
  const [initFinished, setInitFinished] = useState(false);
  const [sessionResolved, setSessionResolved] = useState(false);
  const chatBodyRef = useRef<HTMLDivElement | null>(null);

  async function initSession() {
    try {
      setInitStarted(true);
      setInitFinished(false);
      setLoading(true);
      setError(null);
      const session = await createSession();
      setSessionResolved(true);
      setSessionId(session.session_id);
      setApiState(session);
      setMessages(assistantMessagesFromResponse(session));
      setInputText("");
      setContactName("");
      setContactPhone("");
      setVerificationCode("");
      setCodeRequested(false);
      setDevCode(null);
      setResultAccessToken(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать сессию");
    } finally {
      setInitFinished(true);
      setLoading(false);
    }
  }

  useEffect(() => {
    void initSession();
  }, []);

  useEffect(() => {
    if (!loading) return;
    const timeoutId = window.setTimeout(() => {
      setLoading(false);
      setError((current) => current || "Загрузка сессии заняла слишком много времени. Нажмите «Попробовать снова». ");
    }, 15000);
    return () => window.clearTimeout(timeoutId);
  }, [loading]);

  useEffect(() => {
    const body = chatBodyRef.current;
    if (!body) return;
    body.scrollTop = body.scrollHeight;
  }, [messages, apiState, codeRequested, error]);

  useEffect(() => {
    if (!apiState || apiState.input_mode !== "contact") return;
    const prefilledName = typeof apiState.meta.prefilled_name === "string" ? apiState.meta.prefilled_name : "";
    const prefilledPhone = typeof apiState.meta.prefilled_phone === "string" ? apiState.meta.prefilled_phone : "";
    setContactName((current) => current || prefilledName);
    setContactPhone((current) => current || formatRussianPhone(prefilledPhone));
  }, [apiState]);

  useEffect(() => {
    if (!sessionId || typeof window === "undefined") return;
    const storedToken = window.sessionStorage.getItem(`shadow-house-access:${sessionId}`);
    if (storedToken) {
      setResultAccessToken(storedToken);
    }
  }, [sessionId]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const media = window.matchMedia("(max-width: 820px)");
    const syncViewport = (event?: MediaQueryListEvent) => {
      setIsMobileFlow(event ? event.matches : media.matches);
    };

    syncViewport();
    media.addEventListener("change", syncViewport);
    return () => media.removeEventListener("change", syncViewport);
  }, []);

  useEffect(() => {
    if (!apiState) return;
    const hasUserAnswers = messages.some((message) => message.role === "user");
    if (hasUserAnswers || apiState.input_mode === "contact" || apiState.input_mode === "done") {
      setMobileFlowStarted(true);
    }
  }, [apiState, messages]);

  const canSendText = useMemo(() => apiState?.input_mode === "text" && !sending, [apiState?.input_mode, sending]);
  const canSendChoices = useMemo(() => apiState?.input_mode === "choices" && !sending, [apiState?.input_mode, sending]);
  const canSendDepthText = useMemo(
    () => apiState?.input_mode === "choices" && typeof apiState.meta?.depth_key === "string" && !sending,
    [apiState, sending]
  );
  const isFinalPassport = apiState?.meta?.final_offer === true;
  const canShowFinalRestart = Boolean(isFinalPassport);
  const canShowContactGate = useMemo(() => apiState?.input_mode === "contact", [apiState?.input_mode]);
  const canShowUnlockedResult = useMemo(
    () => apiState?.input_mode === "done" && apiState?.meta?.result_unlocked === true,
    [apiState]
  );
  const currentAssistantSections = useMemo(
    () => (apiState ? splitAssistantMessage(sanitizeAssistantMessage(apiState), apiState.input_mode) : []),
    [apiState]
  );
  const mobileStepLabel = apiState?.progress.label || "Первый замер";
  const mobileShadowTitle =
    apiState && typeof apiState.meta?.shadow_id === "number" && apiState.meta.shadow_id <= 3 && typeof apiState.meta?.shadow_name === "string"
      ? `Тень. ${apiState.meta.shadow_name}.`
      : null;
  const mobileStepTitle = apiState
    ? apiState.input_mode === "contact"
      ? "Результат готов"
      : apiState.input_mode === "done" || isFinalPassport
        ? "Паспорт тени"
        : mobileShadowTitle || mobileStepLabel
    : "КЭТ • Тень дома";
  const mobileStepNumber = apiState ? Math.min(Math.max(apiState.progress.current || 1, 1), apiState.progress.total || 1) : 1;
  const mobileSubmitLabel = apiState && apiState.progress.current < apiState.progress.total ? "Далее" : "Отправить";
  const startupErrorMessage = error || "Не удалось подключиться к диагностике. Проверьте API и попробуйте снова.";

  function handlePhoneBlur() {
    setContactPhone((current) => formatRussianPhone(current));
  }

  async function handleTextSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!sessionId || !apiState || !inputText.trim()) return;

    const userText = inputText.trim();
    setInputText("");
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", text: userText },
    ]);
    setSending(true);
    setError(null);

    try {
      const nextState = await sendMessage(sessionId, { text: userText });
      setApiState(nextState);
      setMessages((prev) => [
        ...prev,
        ...assistantMessagesFromResponse(nextState),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка при отправке");
    } finally {
      setSending(false);
    }
  }

  async function handleChoice(choice: string, label: string) {
    if (!sessionId || !apiState) return;

    const shouldShowChoiceMessage = !["go", "collect_passport"].includes(choice);
    if (shouldShowChoiceMessage) {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user", text: `${choice}) ${label}` },
      ]);
    }
    setSending(true);
    setError(null);

    try {
      const nextState = await sendMessage(sessionId, { choice });
      setApiState(nextState);
      setMessages((prev) => [
        ...prev,
        ...assistantMessagesFromResponse(nextState),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка при отправке");
    } finally {
      setSending(false);
    }
  }

  function handleDiagnosticClick(event: MouseEvent<HTMLElement>) {
    if (!sessionId) return;
    const link = event.target instanceof Element ? event.target.closest("a") : null;
    if (link?.getAttribute("href") === "/downloads/checklist-shadow.pdf") {
      recordBonusDownload(sessionId);
    }
    if (link?.getAttribute("href") === "/downloads/blueprint-offer.pdf") {
      recordBlueprintOpen(sessionId);
    }
  }

  async function handleRequestCode() {
    if (!sessionId) return;
    const phoneValidation = validateRussianPhone(contactPhone);
    if (!phoneValidation.normalized) {
      setError(phoneValidation.error);
      return;
    }

    setSendingCode(true);
    setError(null);

    try {
      const response = await requestPhoneCode(sessionId, {
        display_name: contactName.trim(),
        phone_number: phoneValidation.normalized,
      });
      setContactName(response.contact_name);
      setContactPhone(formatRussianPhone(response.phone_number));
      setCodeRequested(true);
      setDevCode(response.dev_code ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить код");
    } finally {
      setSendingCode(false);
    }
  }

  async function handleVerifyCode() {
    if (!sessionId) return;
    const phoneValidation = validateRussianPhone(contactPhone);
    if (!phoneValidation.normalized) {
      setError(phoneValidation.error);
      return;
    }

    setVerifyingCode(true);
    setError(null);

    try {
      const response = await verifyPhoneCode(sessionId, {
        phone_number: phoneValidation.normalized,
        code: verificationCode.trim(),
      });
      setResultAccessToken(response.access_token);
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(`shadow-house-access:${sessionId}`, response.access_token);
      }
      setApiState(response.response);
      setMessages((prev) => [...prev, ...assistantMessagesFromResponse(response.response)]);
      setCodeRequested(false);
      setDevCode(null);
      setVerificationCode("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось подтвердить код");
    } finally {
      setVerifyingCode(false);
    }
  }

  async function handleRestart() {
    clearStoredAccessTokens();
    if (!sessionId) {
      await initSession();
      return;
    }

    try {
      setSending(true);
      setError(null);
      const session = await resetSession(sessionId);
      setSessionId(session.session_id);
      setApiState(session);
      setMessages(assistantMessagesFromResponse(session));
      setInputText("");
      setContactName("");
      setContactPhone("");
      setVerificationCode("");
      setCodeRequested(false);
      setDevCode(null);
      setResultAccessToken(null);
      setMobileFlowStarted(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось начать заново");
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <main className="page">
        <div className="shell">
          <div className="loadingCard">КЭТ готовит вход в диагностику «Тень дома»…</div>
          <pre className="errorBox" style={{ marginTop: 12, whiteSpace: "pre-wrap" }}>
            {`debug: loading=${String(loading)}
apiState=${apiState ? "yes" : "no"}
error=${error || "none"}
sessionId=${sessionId || "none"}
initStarted=${String(initStarted)}
initFinished=${String(initFinished)}
sessionResolved=${String(sessionResolved)}`}
          </pre>
        </div>
      </main>
    );
  }

  if (!apiState) {
    return (
      <main className={`page${isMobileFlow ? " mobilePage" : ""}`}>
        <div className={isMobileFlow ? "mobileShell mobileShellIntro" : "shell"}>
          <section className={isMobileFlow ? "mobileIntroCard startupCard" : "loadingCard startupCard"}>
            <div className={isMobileFlow ? "mobileIntroEyebrow" : "moduleTag"}>КЭТ • Тень дома</div>
            <h1>Диагностика временно не открылась</h1>
            <p>
              Фон загрузился, но основной сценарий не получил стартовую сессию от API. Обычно это происходит, когда
              frontend смотрит на неверный адрес backend после деплоя.
            </p>
            <div className="errorBox startupError">{startupErrorMessage}</div>
            <button type="button" className="submitButton startupRetryButton" onClick={() => void initSession()}>
              Попробовать снова
            </button>
          </section>
        </div>
      </main>
    );
  }

  if (isMobileFlow) {
    const showMobileIntro = !mobileFlowStarted && Boolean(apiState) && isInteractiveStep(apiState);
    const mobileIntroTotalSteps = apiState?.progress.total ?? 16;
    const stepEyebrow =
      apiState?.input_mode === "contact"
        ? "Подтверждение доступа"
        : apiState?.input_mode === "done"
          ? "Финальный экран"
          : "Текущий шаг";

    return (
      <main className="page mobilePage" onClickCapture={handleDiagnosticClick}>
        <div className={`mobileShell${showMobileIntro ? " mobileShellIntro" : ""}`}>
          {showMobileIntro ? (
            <section className="mobileIntroCard">
              <div className="mobileIntroEyebrow">КЭТ • Тень дома</div>
              <h1>Первый замер скрытой трещины</h1>
              <p>
                Это первый модуль системы «Дом». Здесь мы не разбираем всю жизнь, а находим один важный узел, который
                влияет на дальнейшую стройку.
              </p>
              <p>
                В конце вы получите короткий и понятный результат. Диагностика проходит пошагово, спокойно и без
                лишней ленты сообщений.
              </p>
              <div className="mobileIntroMeta">
                <span>{mobileIntroTotalSteps} шагов</span>
                <span>примерно 7–10 минут</span>
              </div>
              <button type="button" className="submitButton mobileIntroButton" onClick={() => setMobileFlowStarted(true)}>
                Начать
              </button>
            </section>
          ) : (
            <>
              {apiState && !isFinalPassport ? (
                <header className="mobileProgressHeader">
                  <div className="mobileProgressTopline">
                    <div>
                      <div className="mobileProgressBrand">КЭТ • Тень дома</div>
                      <div className="mobileProgressStage">{mobileStepLabel}</div>
                    </div>
                    <div className="mobileProgressMeta">Шаг {mobileStepNumber} из {apiState.progress.total}</div>
                  </div>
                  <ProgressBar
                    current={apiState.progress.current}
                    total={apiState.progress.total}
                    label={apiState.progress.label}
                    compact
                  />
                </header>
              ) : null}

              {error ? <div className="errorBox mobileErrorBox">{error}</div> : null}

              <section className="mobileStepScreen">
                {apiState?.input_mode === "contact" ? (
                  <div className="mobileStepCard mobileStepCardContact">
                    <ContactGateCard
                      name={contactName}
                      phone={contactPhone}
                      code={verificationCode}
                      sendingCode={sendingCode}
                      verifyingCode={verifyingCode}
                      codeRequested={codeRequested}
                      devCode={devCode}
                      onNameChange={setContactName}
                      onPhoneChange={setContactPhone}
                      onPhoneBlur={handlePhoneBlur}
                      onCodeChange={setVerificationCode}
                      onRequestCode={handleRequestCode}
                      onVerifyCode={handleVerifyCode}
                    />
                  </div>
                ) : apiState?.input_mode === "done" ? (
                  <div className="mobileResultScreen">
                    <div className="mobileStepCard mobileResultCard">
                      <div className="mobileStepEyebrow">{stepEyebrow}</div>
                      <h2>{mobileStepTitle}</h2>
                      <div className="mobileResultBody">
                        {currentAssistantSections.map((section, index) => (
                          <div key={`${index}-${section.slice(0, 18)}`}>
                            {renderStructuredSection(section, `result-${index}`, { resultMode: true })}
                          </div>
                        ))}
                      </div>
                    </div>

                    {canShowUnlockedResult ? (
                      <div className="doneBox mobileDoneBox">
                        <div className="doneTitle">Паспорт тени готов</div>
                        <p>
                          Сейчас у тебя есть первый замер скрытой трещины. Это ещё не весь Дом, но уже важная опора перед
                          следующим шагом.
                        </p>
                        {resultAccessToken ? (
                          <p className="doneMeta">Текущая сессия подтверждена по телефону и связана с сохранённым результатом.</p>
                        ) : null}
                        <button type="button" className="submitButton" onClick={() => void handleRestart()}>
                          Пройти заново
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <>
                    <div className="mobileStepCard">
                      {!isFinalPassport ? (
                        <>
                          <div className="mobileStepEyebrow">{stepEyebrow}</div>
                          <h2>{mobileStepTitle}</h2>
                        </>
                      ) : null}
                      <div className="mobileStepContent">
                        {currentAssistantSections.map((section, index) => (
                          <div key={`${index}-${section.slice(0, 18)}`}>
                            {renderStructuredSection(section, `step-${index}`, { hideShadowHeading: Boolean(mobileShadowTitle) })}
                          </div>
                        ))}
                      </div>
                    </div>

                    {canSendChoices && apiState && (apiState.choices.length > 0 || canShowFinalRestart) ? (
                      <div className="mobileActionDock">
                        {apiState.choices.length > 0 ? (
                          <ChoiceButtons choices={apiState.choices} onChoose={handleChoice} disabled={sending} />
                        ) : null}
                        {canShowFinalRestart ? (
                          <button type="button" className="submitButton restartButton" onClick={() => void handleRestart()} disabled={sending}>
                            Пройти заново
                          </button>
                        ) : null}
                      </div>
                    ) : null}

                    {canSendText ? (
                      <div className="mobileActionDock">
                        <form className="textForm mobileTextForm" onSubmit={handleTextSubmit}>
                          <textarea
                            className="textInput"
                            placeholder="Напишите ответ..."
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            disabled={sending}
                            rows={4}
                          />
                          <button type="submit" className="submitButton" disabled={sending || !inputText.trim()}>
                            {sending ? "Отправка…" : mobileSubmitLabel}
                          </button>
                        </form>
                      </div>
                    ) : null}

                    {canSendDepthText ? (
                      <div className="mobileActionDock">
                        <form className="textForm mobileTextForm" onSubmit={handleTextSubmit}>
                          <textarea
                            className="textInput"
                            placeholder="Или напишите свой вариант..."
                            value={inputText}
                            onChange={(e) => setInputText(e.target.value)}
                            disabled={sending}
                            rows={3}
                          />
                          <button type="submit" className="submitButton" disabled={sending || !inputText.trim()}>
                            {sending ? "Отправка…" : "Отправить свой вариант"}
                          </button>
                        </form>
                      </div>
                    ) : null}
                  </>
                )}
              </section>
            </>
          )}
        </div>
      </main>
    );
  }

  return (
    <main className="page" onClickCapture={handleDiagnosticClick}>
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">КЭТ · Тень дома</div>
          <div className="moduleTag">Первый замер скрытой трещины</div>
          <p className="sidebarText">
            Это не разбор всей жизни и не отдельный психологический опросник. КЭТ помогает найти одну скрытую трещину,
            которая может мешать дальнейшей стройке Дома.
          </p>
          {apiState && (
            <ProgressBar
              current={apiState.progress.current}
              total={apiState.progress.total}
              label={apiState.progress.label}
            />
          )}
          <div className="tips">
            <div className="tipTitle">Как идти по модулю</div>
            <ul>
              <li>отвечай коротко, честно и по ощущению;</li>
              <li>не ищи «правильный» ответ;</li>
              <li>если что-то неприятно откликается — именно там и может быть трещина.</li>
            </ul>
          </div>
          <div className="moduleNote">
            После этого модуля будет видно не весь Дом, а только один важный узел, который стоит учесть до следующих шагов.
          </div>
          {sessionId && <div className="sessionInfo">Контур сессии: {sessionId}</div>}
        </aside>

        <section className="chatCard">
          <div className="chatHeader">
            <div>
              <h1>КЭТ ведет модуль «Тень дома»</h1>
              <p>Вводная архитектурная диагностика скрытой трещины перед дальнейшей стройкой Дома</p>
            </div>
          </div>

          <div className="chatBody" ref={chatBodyRef}>
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </div>

          {error ? <div className="errorBox">{error}</div> : null}

          <div className="chatFooter">
            {canSendChoices && apiState && (apiState.choices.length > 0 || canShowFinalRestart) ? (
              <>
                {apiState.choices.length > 0 ? (
                  <ChoiceButtons choices={apiState.choices} onChoose={handleChoice} disabled={sending} />
                ) : null}
                {canShowFinalRestart ? (
                  <button type="button" className="submitButton restartButton" onClick={() => void handleRestart()} disabled={sending}>
                    Пройти заново
                  </button>
                ) : null}
              </>
            ) : null}

            {canShowContactGate ? (
              <ContactGateCard
                name={contactName}
                phone={contactPhone}
                code={verificationCode}
                sendingCode={sendingCode}
                verifyingCode={verifyingCode}
                codeRequested={codeRequested}
                devCode={devCode}
                onNameChange={setContactName}
                onPhoneChange={setContactPhone}
                onPhoneBlur={handlePhoneBlur}
                onCodeChange={setVerificationCode}
                onRequestCode={handleRequestCode}
                onVerifyCode={handleVerifyCode}
              />
            ) : null}

            {canSendText ? (
              <form className="textForm" onSubmit={handleTextSubmit}>
                <textarea
                  className="textInput"
                  placeholder="Напишите ответ..."
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  disabled={sending}
                  rows={4}
                />
                <button type="submit" className="submitButton" disabled={sending || !inputText.trim()}>
                  {sending ? "Отправка…" : "Отправить"}
                </button>
              </form>
            ) : null}

            {canSendDepthText ? (
              <form className="textForm" onSubmit={handleTextSubmit}>
                <textarea
                  className="textInput"
                  placeholder="Или напишите свой вариант..."
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  disabled={sending}
                  rows={3}
                />
                <button type="submit" className="submitButton" disabled={sending || !inputText.trim()}>
                  {sending ? "Отправка…" : "Отправить свой вариант"}
                </button>
              </form>
            ) : null}

            {canShowUnlockedResult ? (
              <div className="doneBox">
                <div className="doneTitle">Паспорт тени готов</div>
                <p>Сейчас у тебя есть первый замер скрытой трещины. Это ещё не весь Дом, но уже важная опора перед следующим шагом.</p>
                {resultAccessToken ? <p className="doneMeta">Текущая сессия подтверждена по телефону и связана с сохранённым результатом.</p> : null}
                <button type="button" className="submitButton" onClick={() => void handleRestart()}>
                  Пройти заново
                </button>
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </main>
  );
}
