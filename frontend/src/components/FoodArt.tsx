export function FoodArt({
  variant = "plate",
  compact = false,
}: {
  variant?: "plate" | "salad" | "fruit" | "grain";
  compact?: boolean;
}) {
  const emoji = { plate: "🥗", salad: "🥬", fruit: "🍊", grain: "🍚" }[variant];
  return (
    <div
      className={`food-art food-art--${variant} ${compact ? "food-art--compact" : ""}`}
      aria-hidden="true"
    >
      <span className="food-art__orb" />
      <span className="food-art__emoji">{emoji}</span>
      <span className="food-art__spark food-art__spark--one">✦</span>
      <span className="food-art__spark food-art__spark--two">✦</span>
    </div>
  );
}
