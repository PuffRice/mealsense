export type Gender = "" | "male" | "female" | "other";
export type Profile = {
  profile_picture_url?: string | null;
  timezone: string;
  units: string;
  phone?: string | null;
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
  username: string;
  display_name: string;
  profile: Profile;
};
export type Food = {
  id: string;
  name: string;
  name_bn?: string;
  category: string;
  kcal_100g: string | null;
  protein_100g: string | null;
  carbs_100g: string | null;
  fat_100g: string | null;
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
export type VLMAnalysis = {
  food_name: string;
  canonical_catalog_name?: string;
  food_class?: string;
  classification?: {
    predicted_label: string;
    confidence: number;
  };
  portion?: {
    estimated_weight_g: number | null;
    portion_description?: string;
    visual_portion_estimate?: string;
  };
  ingredients?: {
    name: string;
    estimated_weight_g: number | null;
    calories_kcal?: number | null;
    protein_g?: number | null;
    carbohydrates_g?: number | null;
    fat_g?: number | null;
    fiber_g?: number | null;
    matched_fctb?: string | null;
    source_type?: string;
  }[];
  nutrition?: {
    calories_kcal: number | null;
    protein_g: number | null;
    carbohydrates_g: number | null;
    fat_g: number | null;
    fiber_g?: number | null;
  };
  micronutrients?: {
    iron_mg?: number | null;
    calcium_mg?: number | null;
    potassium_mg?: number | null;
  };
  confidence?: {
    food_identification?: number;
    portion_estimation?: number;
    nutrition_estimation?: number;
  };
  warnings?: string[];
  explanation?: string;
};
export type Candidate = {
  name: string;
  model_label?: string;
  category: string;
  confidence: number;
  food_id: string | null;
  result_id?: string;
  analysis?: VLMAnalysis;
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
export type DoctorAccessRequest = {
  id: string;
  doctor_name: string;
  identifier_type: "email" | "phone";
  identifier: string;
  status: "pending" | "approved" | "denied" | "revoked";
  created_at: string;
  approved_at: string | null;
  expires_at: string | null;
  denied_at: string | null;
  revoked_at: string | null;
};
export type DoctorStatus = {
  status: "pending" | "approved" | "denied" | "revoked" | "expired";
  active: boolean;
  created_at: string;
  patient_name?: string;
  patient_timezone?: string;
  approved_at?: string;
  expires_at?: string;
};
export type DoctorMealItem = {
  food_name: string;
  grams: string;
  kcal: string;
  protein_g: string;
  carbs_g: string;
  fat_g: string;
  nutrition_source_snapshot: string;
};
export type DoctorMeal = {
  id: string;
  eaten_at: string;
  local_date: string;
  meal_type: string;
  items: DoctorMealItem[];
  totals: MacroTotals;
};
export type DoctorHistory = {
  count: number;
  limit: number;
  offset: number;
  meals: DoctorMeal[];
};
export type DoctorFoodStat = {
  food_name: string;
  times: number;
  grams: string;
  kcal: string;
};
export type DoctorMonthly = {
  month: string;
  meals: number;
  item_count: number;
  kcal: string;
  protein_g: string;
  carbs_g: string;
  fat_g: string;
  grams: string;
};
export type DoctorMealTypeStat = {
  meal_type: string;
  meals: number;
  item_count: number;
  kcal: string;
  grams: string;
};
export type DoctorAnalytics = {
  range: { from: string; to: string };
  totals: MacroTotals & { items: number; grams: string };
  meals_logged: number;
  items_logged: number;
  logged_days: number;
  avg_kcal_per_logged_day: string;
  most_consumed: (DoctorFoodStat & {
    protein_g: string;
    carbs_g: string;
    fat_g: string;
  })[];
  food_frequency: DoctorFoodStat[];
  monthly: DoctorMonthly[];
  daily: (Omit<DoctorMonthly, "month"> & { day: string })[];
  by_meal_type: DoctorMealTypeStat[];
};
