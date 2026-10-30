export type Profile = {
  timezone: string;
  units: string;
  daily_kcal_goal: number;
  protein_goal_g: number;
  carbs_goal_g: number;
  fat_goal_g: number;
};
export type User = {
  id: string;
  email: string;
  display_name: string;
  profile: Profile;
};
export type Food = {
  id: string;
  name: string;
  category: string;
  kcal_100g: string;
  protein_100g: string;
  carbs_100g: string;
  fat_100g: string;
  source: string;
  is_sample: boolean;
};
export type MacroTotals = {
  kcal: string;
  protein_g: string;
  carbs_g: string;
  fat_g: string;
};
export type MealItem = {
  id: string;
  food: string;
  food_name: string;
  grams: string;
  kcal: string;
  protein_g: string;
  carbs_g: string;
  fat_g: string;
};
export type Meal = {
  id: string;
  eaten_at: string;
  meal_type: "breakfast" | "lunch" | "dinner" | "snack";
  notes: string;
  version: number;
  image: string | null;
  items: MealItem[];
  totals: MacroTotals;
};
export type Daily = { date: string; totals: MacroTotals; meal_count: number };
export type MealInput = {
  eaten_at: string;
  meal_type: Meal["meal_type"];
  notes: string;
  image_id?: string | null;
  items: { food_id: string; grams: number }[];
  version?: number;
  operation_id?: string;
};
