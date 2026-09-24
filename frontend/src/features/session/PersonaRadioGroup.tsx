import type { Persona, PersonaOption } from "../../api/types";

export interface PersonaRadioGroupProps {
  options: PersonaOption[];
  selected: Persona | null;
  onChange: (persona: Persona) => void;
}

/** AC1: exactly the four personas, as a keyboard-operable radio group
 * (native radios: arrow keys move selection, Tab moves focus, all with the
 * browser's built-in focus-visible outline plus the shared one in
 * `app/theme.css`). */
export function PersonaRadioGroup({ options, selected, onChange }: PersonaRadioGroupProps): JSX.Element {
  return (
    <fieldset>
      <legend>Persona (exactly four)</legend>
      <div>
        {options.map((option) => (
          <label key={option.persona}>
            <input
              type="radio"
              name="persona"
              value={option.persona}
              checked={selected === option.persona}
              onChange={() => onChange(option.persona)}
            />
            <strong>{option.display_name}</strong> <code>{option.persona}</code>
            <br />
            <span>
              {option.description}
              {option.requires_customer_binding ? " Requires choosing one seeded demo customer." : ""}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
