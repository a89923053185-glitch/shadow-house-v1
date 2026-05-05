import { ChoiceOption } from "@/lib/types";

const HIDDEN_SERVICE_KEYS = new Set(["go", "yes", "no", "collect_passport"]);

function displayLabelFor(choice: ChoiceOption) {
  if (!HIDDEN_SERVICE_KEYS.has(choice.key)) return choice.label;

  return choice.label.replace(new RegExp(`^\\s*${choice.key}\\s+`), "");
}

type Props = {
  choices: ChoiceOption[];
  onChoose: (value: string, label: string) => void;
  disabled?: boolean;
};

export function ChoiceButtons({ choices, onChoose, disabled = false }: Props) {
  return (
    <div className="choicesGrid">
      {choices.map((choice) => {
        const showKey = choice.key !== choice.label && !HIDDEN_SERVICE_KEYS.has(choice.key);
        const displayLabel = displayLabelFor(choice);

        return (
          <button
            key={choice.key}
            type="button"
            className="choiceButton"
            disabled={disabled}
            onClick={() => onChoose(choice.key, choice.label)}
          >
            {showKey ? <span className="choiceKey">{choice.key}</span> : null}
            <span>{displayLabel}</span>
          </button>
        );
      })}
    </div>
  );
}
