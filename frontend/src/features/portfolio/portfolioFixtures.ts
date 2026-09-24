import type { PortfolioItem } from "../../api/types";

/**
 * The design mockup's 14-row static demo dataset
 * (specs/design/mockups/E3-S3.html `RAW`/`ITEMS`), ported verbatim as a
 * realistic synthetic fixture for this feature's tests. Names, account ids
 * and customer ids are fictional (CLAUDE.md: synthetic data only).
 */
type RawRow = [
  accountId: string,
  customerId: string,
  customerName: string,
  accountType: PortfolioItem["account_type"],
  outstandingBalance: string,
  overdueAmount: string,
  dpd: number,
  status: PortfolioItem["collection_status"],
  priorityBand: PortfolioItem["priority_band"],
  priorityScore: string,
  humanTreatment: boolean,
  recordVersion: number,
];

const RAW: RawRow[] = [
  ["acc_000123", "cus_0041", "Priya Raman", "CARD", "4820.35", "612.40", 47, "IN_PROGRESS", "HIGH", "79.70", false, 7],
  ["acc_000131", "cus_0052", "Marcus Feldman", "PERSONAL_LOAN", "18250.00", "1875.00", 92, "ESCALATED", "HIGH", "91.15", true, 12],
  ["acc_000142", "cus_0067", "Elena Vasquez", "CARD", "2310.80", "245.10", 12, "NEW", "LOW", "24.60", false, 3],
  ["acc_000157", "cus_0073", "Tobias Lindqvist", "PERSONAL_LOAN", "9400.00", "940.00", 33, "PTP_PENDING", "MEDIUM", "55.30", false, 5],
  ["acc_000164", "cus_0081", "Amara Nwosu", "CARD", "7120.45", "1320.00", 68, "IN_PROGRESS", "HIGH", "82.40", false, 9],
  ["acc_000178", "cus_0090", "Jonas Whitfield", "CARD", "980.00", "120.00", 5, "NEW", "LOW", "12.05", false, 2],
  ["acc_000185", "cus_0094", "Sofia Marchetti", "PERSONAL_LOAN", "26700.00", "2225.00", 61, "ARRANGEMENT_ACTIVE", "MEDIUM", "63.85", false, 8],
  ["acc_000193", "cus_0102", "Devon Achterberg", "CARD", "3560.20", "410.55", 29, "IN_PROGRESS", "MEDIUM", "48.20", false, 4],
  ["acc_000206", "cus_0115", "Hana Kobayashi", "CARD", "5205.90", "890.30", 104, "ESCALATED", "HIGH", "95.60", true, 15],
  ["acc_000214", "cus_0121", "Liam Osei-Bonsu", "PERSONAL_LOAN", "12480.00", "1040.00", 41, "IN_PROGRESS", "MEDIUM", "58.75", false, 6],
  ["acc_000221", "cus_0133", "Grace Ndlovu", "CARD", "1675.25", "95.00", 8, "NEW", "LOW", "15.40", false, 2],
  ["acc_000230", "cus_0140", "Rafael Quintero", "PERSONAL_LOAN", "7300.00", "1460.00", 76, "PTP_PENDING", "HIGH", "74.90", false, 10],
  ["acc_000238", "cus_0148", "Ingrid Solberg", "CARD", "4390.10", "530.25", 22, "IN_PROGRESS", "LOW", "33.10", false, 4],
  ["acc_000245", "cus_0156", "Kwame Adjei", "PERSONAL_LOAN", "15900.00", "1325.00", 55, "IN_PROGRESS", "MEDIUM", "61.20", false, 7],
];

function bucketOf(dpd: number): PortfolioItem["bucket"] {
  if (dpd >= 90) return "DPD_90_PLUS";
  if (dpd >= 60) return "DPD_60_89";
  if (dpd >= 30) return "DPD_30_59";
  if (dpd >= 1) return "DPD_1_29";
  return "CURRENT";
}

export const PORTFOLIO_FIXTURE_ITEMS: PortfolioItem[] = RAW.map((row) => ({
  account_id: row[0],
  customer_id: row[1],
  customer_name: row[2],
  account_type: row[3],
  outstanding_balance: row[4],
  overdue_amount: row[5],
  dpd: row[6],
  bucket: bucketOf(row[6]),
  collection_status: row[7],
  priority_band: row[8],
  priority_score: row[9],
  human_treatment: row[10],
  automated_treatment_suppressed: row[10],
  record_version: row[11],
}));
