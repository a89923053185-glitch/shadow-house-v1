type Props = {
  name: string;
  phone: string;
  code: string;
  sendingCode: boolean;
  verifyingCode: boolean;
  codeRequested: boolean;
  devCode?: string | null;
  onNameChange: (value: string) => void;
  onPhoneChange: (value: string) => void;
  onPhoneBlur: () => void;
  onCodeChange: (value: string) => void;
  onRequestCode: () => void;
  onVerifyCode: () => void;
};

export function ContactGateCard({
  name,
  phone,
  code,
  sendingCode,
  verifyingCode,
  codeRequested,
  devCode,
  onNameChange,
  onPhoneChange,
  onPhoneBlur,
  onCodeChange,
  onRequestCode,
  onVerifyCode,
}: Props) {
  return (
    <div className="contactGateCard">
      <div className="contactGateHeader">
        <div className="contactGateEyebrow">Сохранение доступа</div>
        <h2>Результат готов</h2>
        <p>
          Ваш результат уже собран.
          Чтобы открыть его и сохранить доступ к нему, пожалуйста, укажите номер телефона и подтвердите код.
        </p>
      </div>

      <div className="contactFieldGroup">
        <label className="contactField">
          <span>Как к тебе обращаться</span>
          <input value={name} onChange={(e) => onNameChange(e.target.value)} placeholder="Например, Анна" />
        </label>

        <label className="contactField">
          <span>Номер телефона</span>
          <input
            value={phone}
            onChange={(e) => onPhoneChange(e.target.value)}
            onBlur={onPhoneBlur}
            placeholder="+7 (999) 123-45-67"
            inputMode="tel"
            autoComplete="tel"
          />
        </label>
      </div>

      <button type="button" className="submitButton contactActionButton" onClick={onRequestCode} disabled={sendingCode || verifyingCode}>
        {sendingCode ? "Отправляем код…" : codeRequested ? "Получить код повторно" : "Получить код"}
      </button>

      {codeRequested ? (
        <div className="contactVerificationBlock">
          <div className="contactCodeHint">Введите код из сообщения</div>
          <label className="contactField">
            <span>Код подтверждения</span>
            <input
              value={code}
              onChange={(e) => onCodeChange(e.target.value)}
              placeholder="6 цифр"
              inputMode="numeric"
              maxLength={6}
            />
          </label>

          {devCode ? <div className="devOtpHint">Код для локальной проверки: <strong>{devCode}</strong></div> : null}

          <button type="button" className="submitButton contactActionButton" onClick={onVerifyCode} disabled={verifyingCode || sendingCode}>
            {verifyingCode ? "Проверяем код…" : "Подтвердить код"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
