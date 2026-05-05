type Props = {
  current: number;
  total: number;
  label: string;
  compact?: boolean;
};

export function ProgressBar({ current, total, label, compact = false }: Props) {
  const safeTotal = total || 1;
  const percent = Math.max(0, Math.min(100, Math.round((current / safeTotal) * 100)));
  const stepLabel = current > 0 ? `Шаг ${current} из ${safeTotal}` : "Старт диагностики";

  return (
    <div className="progressWrap">
      {!compact ? (
        <div className="progressHeader">
          <span>{label}</span>
          <span>{stepLabel}</span>
        </div>
      ) : null}
      <div className="progressTrack">
        <div className="progressFill" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
