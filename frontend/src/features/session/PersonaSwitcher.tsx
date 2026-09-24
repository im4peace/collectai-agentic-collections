import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { createSession } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { Persona } from "../../api/types";
import { setSession } from "../../auth/sessionStore";
import { defaultRouteForCapabilities } from "../../lib/navLinks";
import { DemoCustomerSelect } from "./DemoCustomerSelect";
import { PersonaRadioGroup } from "./PersonaRadioGroup";
import { useSessionOptions } from "./useSessionOptions";

const CUSTOMER_SELECT_ID = "demo-customer-select";

/**
 * AC1: the demo persona switcher. Lists exactly the four personas
 * (`GET /api/session/options`), requires a seeded demo customer for
 * CUSTOMER before the request is even sent, then `POST /api/session` binds
 * the chosen persona (and, for CUSTOMER, the customer) server-side and
 * routes to that persona's first permitted screen.
 */
export function PersonaSwitcher(): JSX.Element {
  const { data, error, loading } = useSessionOptions();
  const navigate = useNavigate();
  const [selectedPersona, setSelectedPersona] = useState<Persona | null>(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (loading) {
    return <p role="status">Loading persona options...</p>;
  }
  if (error !== null || data === null) {
    return <p role="alert">{error ?? "Persona options could not be loaded."}</p>;
  }

  const selectedOption = data.personas.find((option) => option.persona === selectedPersona) ?? null;
  const requiresCustomer = selectedOption?.requires_customer_binding ?? false;

  function handlePersonaChange(persona: Persona): void {
    setSelectedPersona(persona);
    setValidationError(null);
    setSubmitError(null);
    if (persona !== "CUSTOMER") {
      setSelectedCustomerId("");
    }
  }

  async function submitPersona(): Promise<void> {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const info = await createSession(
        requiresCustomer && selectedPersona !== null
          ? { persona: selectedPersona, customer_id: selectedCustomerId }
          : { persona: selectedPersona as Persona },
      );
      setSession(info);
      navigate(defaultRouteForCapabilities(info.capabilities));
    } catch (caught) {
      setSubmitError(caught instanceof ApiError ? caught.body.message : "Could not switch persona.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (selectedPersona === null) {
      return;
    }
    // AC1: CUSTOMER requires choosing a demo customer before the request is
    // sent at all, not just relying on the server's 422.
    if (requiresCustomer && selectedCustomerId === "") {
      setValidationError("Choose one seeded demo customer before continuing as CUSTOMER.");
      document.getElementById(CUSTOMER_SELECT_ID)?.focus();
      return;
    }
    setValidationError(null);
    void submitPersona();
  }

  return (
    <div>
      <h1>Persona switcher</h1>
      <p>
        Demo-only. Choosing a persona changes the header sent on later API calls. It is not
        authentication.
      </p>
      <form aria-label="Switch persona" onSubmit={handleSubmit} noValidate>
        {submitError !== null && <p role="alert">{submitError}</p>}
        <PersonaRadioGroup
          options={data.personas}
          selected={selectedPersona}
          onChange={handlePersonaChange}
        />
        {requiresCustomer && (
          <>
            {validationError !== null && <p role="alert">{validationError}</p>}
            <DemoCustomerSelect
              id={CUSTOMER_SELECT_ID}
              customers={data.demo_customers}
              value={selectedCustomerId}
              onChange={(customerId) => {
                setSelectedCustomerId(customerId);
                setValidationError(null);
              }}
              invalid={validationError !== null}
            />
          </>
        )}
        <button type="submit" disabled={selectedPersona === null || submitting}>
          Use this persona
        </button>
      </form>
    </div>
  );
}
