import type { Gender } from "../../lib/types";

export type ExactAge = {
  years: number;
  months: number;
  days: number;
};

export function getTodayIso(): string {
  return new Date().toISOString().slice(0, 10);
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

export type BmiSuggestion = {
  bmi: number;
  category: "Underweight" | "Healthy weight" | "Overweight" | "Obese";
  tone: "peach" | "green" | "neutral";
  focus: string;
  healthyMinKg: number;
  healthyMaxKg: number;
  kcal: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
};

export function computeBmiAndSuggestions(
  heightCm: number,
  weightKg: number,
  gender: Gender,
  ageYears: number | null,
): BmiSuggestion | null {
  if (
    !Number.isFinite(heightCm) ||
    !Number.isFinite(weightKg) ||
    heightCm < 50 ||
    heightCm > 260 ||
    weightKg < 20 ||
    weightKg > 350
  ) {
    return null;
  }
  const heightM = heightCm / 100;
  const bmi = weightKg / (heightM * heightM);
  const healthyMinKg = Math.round(18.5 * heightM * heightM * 10) / 10;
  const healthyMaxKg = Math.round(24.9 * heightM * heightM * 10) / 10;

  const effectiveAge = ageYears !== null && ageYears >= 10 ? ageYears : 25;
  const genderOffset = gender === "male" ? 5 : gender === "female" ? -161 : -78;
  const bmr = 10 * weightKg + 6.25 * heightCm - 5 * effectiveAge + genderOffset;
  const tdee = bmr * 1.375;

  let category: BmiSuggestion["category"] = "Healthy weight";
  let tone: BmiSuggestion["tone"] = "green";
  let targetKcal = tdee;
  let proteinPerKg = 1.6;
  let fatShare = 0.28;
  let focus = "Balanced daily maintenance for healthy BMI.";

  if (bmi < 18.5) {
    category = "Underweight";
    tone = "peach";
    targetKcal = tdee + 300;
    proteinPerKg = 1.8;
    fatShare = 0.28;
    focus =
      "Gentle calorie surplus (+300 kcal) to support healthy weight gain.";
  } else if (bmi < 25) {
    category = "Healthy weight";
    tone = "green";
    targetKcal = tdee;
    proteinPerKg = 1.6;
    fatShare = 0.28;
    focus = "Balanced maintenance energy for your current BMI.";
  } else if (bmi < 30) {
    category = "Overweight";
    tone = "peach";
    targetKcal = tdee - 300;
    proteinPerKg = 1.8;
    fatShare = 0.27;
    focus =
      "Gentle deficit (-300 kcal) with higher protein for steady progress.";
  } else {
    category = "Obese";
    tone = "peach";
    targetKcal = tdee - 450;
    proteinPerKg = 1.6;
    fatShare = 0.26;
    focus =
      "Supportive calorie deficit (-450 kcal) prioritizing protein satiety.";
  }

  const kcal = Math.round(Math.min(4000, Math.max(1200, targetKcal)) / 10) * 10;
  const protein_g = Math.round(
    Math.min((kcal * 0.35) / 4, Math.max(50, weightKg * proteinPerKg)),
  );
  const fat_g = Math.round((kcal * fatShare) / 9);
  const remainingKcal = Math.max(0, kcal - protein_g * 4 - fat_g * 9);
  const carbs_g = Math.round(remainingKcal / 4);

  return {
    bmi: Math.round(bmi * 10) / 10,
    category,
    tone,
    focus,
    healthyMinKg,
    healthyMaxKg,
    kcal,
    protein_g,
    carbs_g,
    fat_g,
  };
}
