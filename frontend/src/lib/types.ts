export type Gender = "" | "male" | "female" | "other";
export type Profile = {
  timezone: string;
  units: string;
  gender?: Gender;
  date_of_birth?: string | null;
  height_cm?: string | number | null;
  weight_kg?: string | number | null;
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
  name_bn?: string;
  category: string;
  kcal_100g: string;
  protein_100g: string;
  carbs_100g: string;
  fat_100g: string;
  source: string;
  is_sample: boolean;
  is_verified?: boolean;
  servings?: {
    id: number;
    name: string;
    name_bn: string;
    definition: string;
    weight_g: string;
    preparation_state: string;
    is_approximate: boolean;
    is_default: boolean;
  }[];
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
  serving?: number | null;
  kcal: string;
  protein_g: string;
  carbs_g: string;
  fat_g: string;
  recognition_result?: string | null;
  nutrition_source_snapshot?: string;
  nutrition_basis_snapshot?: string;
  calculation_version?: string;
};
export type Candidate = {
  name: string;
  category: string;
  confidence: number;
  food_id: string | null;
  result_id?: string;
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
export type Daily = {
  date: string;
  totals: MacroTotals;
  meal_count: number;
  progress?: {
    nutrient: string;
    actual: string;
    target: string;
    unit: string;
    goal_version: number;
  }[];
};
export type MealInput = {
  eaten_at: string;
  meal_type: Meal["meal_type"];
  notes: string;
  image_id?: string | null;
  items: {
    food_id: string;
    grams: number;
    serving_id?: number;
    recognition_result_id?: string;
  }[];
  version?: number;
  operation_id?: string;
};
