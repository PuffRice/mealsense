export type ExactAge = {
  years: number;
  months: number;
  days: number;
};

export function getTodayIso(timeZone?: string): string {
  const now = new Date();
  if (timeZone) {
    try {
      const parts = new Intl.DateTimeFormat("en-US", {
        timeZone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).formatToParts(now);
      const get = (t: string) => parts.find((p) => p.type === t)?.value || "";
      const y = get("year");
      const m = get("month");
      const d = get("day");
      if (y && m && d) return `${y}-${m}-${d}`;
    } catch {
      // Fall back to local date components below
    }
  }
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function calculateExactAge(
  dob: string | null | undefined,
): ExactAge | null {
  if (!dob) return null;
  const parts = dob.split("-").map(Number);
  if (parts.length !== 3 || parts.some((n) => Number.isNaN(n))) return null;
  const [birthYear, birthMonth, birthDay] = parts;
  const now = new Date();
  const todayYear = now.getFullYear();
  const todayMonth = now.getMonth() + 1;
  const todayDay = now.getDate();

  const birthDate = new Date(birthYear, birthMonth - 1, birthDay);
  const todayDate = new Date(todayYear, todayMonth - 1, todayDay);
  if (birthDate > todayDate || birthYear < 1900) return null;

  let years = todayYear - birthYear;
  let months = todayMonth - birthMonth;
  let days = todayDay - birthDay;

  if (days < 0) {
    months -= 1;
    const prevMonthDays = new Date(todayYear, todayMonth - 1, 0).getDate();
    days += prevMonthDays;
  }
  if (months < 0) {
    years -= 1;
    months += 12;
  }
  return { years, months, days };
}
