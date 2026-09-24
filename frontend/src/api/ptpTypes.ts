/**
 * Wire types for `POST /api/ptps/validate` and `POST /api/ptps`, mirrored
 * from `backend/src/collectai/api/schemas/ptps.py` (E6-S6). Used by Customer
 * 360's officer-facing "Record Promise-to-Pay" form (E4-S2 AC8).
 */
export interface PtpValidateRequest {
  account_id: string;
  promised_amount: string;
  promised_date: string;
}

export interface ValidRangeAlternatives {
  valid_amount_range?: { min: string; max: string };
  valid_date_range?: { earliest: string; latest: string };
}

export interface PtpValidationResult {
  valid: boolean;
  reason_codes: string[];
  alternatives: ValidRangeAlternatives | null;
  policy_version: string;
}

export interface PtpCreateRequest {
  account_id: string;
  promised_amount: string;
  promised_date: string;
  interaction_reference?: string;
  item_id?: string;
  record_version: number;
  snapshot_as_of: string;
}
