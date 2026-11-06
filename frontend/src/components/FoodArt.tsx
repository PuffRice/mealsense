import { Apple, CookingPot, Salad, Utensils } from "lucide-react";

export function FoodArt({
  variant = "plate",
  compact = false,
}: {
  variant?: "plate" | "salad" | "fruit" | "grain";
  compact?: boolean;
}) {
  const Icon = {
    plate: Utensils,
    salad: Salad,
    fruit: Apple,
    grain: CookingPot,
  }[variant];
  return (
    <div
      className={`food-art food-art--${variant} ${compact ? "food-art--compact" : ""}`}
      aria-hidden="true"
    >
      <span className="food-art__emoji">
        <Icon size={compact ? 21 : 64} strokeWidth={1.5} />
      </span>
    </div>
  );
}
