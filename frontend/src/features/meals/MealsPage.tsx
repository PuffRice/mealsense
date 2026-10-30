import { useState } from "react";
import {
  CalendarDays,
  Pencil,
  Plus,
  Search,
  Trash2,
  Utensils,
} from "lucide-react";
import { Badge, Button, Card, EmptyState } from "../../design/ui";
import { FoodArt } from "../../components/FoodArt";
import type { Meal } from "../../lib/types";

export function MealsPage({
  meals,
  timezone,
  onAdd,
  onEdit,
  onDelete,
}: {
  meals: Meal[];
  timezone: string;
  onAdd: () => void;
  onEdit: (meal: Meal) => void;
  onDelete: (meal: Meal) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const visible = meals.filter(
    (meal) =>
      (filter === "all" || meal.meal_type === filter) &&
      meal.items.some((item) =>
        item.food_name.toLowerCase().includes(query.toLowerCase()),
      ),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">YOUR FOOD DIARY</span>
          <h1>My meals</h1>
          <p>A record of what you've eaten, one meal at a time.</p>
        </div>
        <Button icon={<Plus size={18} />} onClick={onAdd}>
          Log a meal
        </Button>
      </div>
      <Card className="list-card">
        <div className="list-toolbar">
          <div className="food-search">
            <Search size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search meals..."
              aria-label="Search meals"
            />
          </div>
          <div
            className="filter-tabs"
            role="group"
            aria-label="Filter by meal type"
          >
            {["all", "breakfast", "lunch", "dinner", "snack"].map((value) => (
              <button
                key={value}
                className={filter === value ? "filter-tabs__active" : ""}
                onClick={() => setFilter(value)}
              >
                {value}
              </button>
            ))}
          </div>
        </div>
        {visible.length ? (
          <div className="meal-list">
            {visible.map((meal) => (
              <article className="meal-list__item" key={meal.id}>
                <FoodArt
                  compact
                  variant={
                    meal.meal_type === "breakfast"
                      ? "fruit"
                      : meal.meal_type === "dinner"
                        ? "grain"
                        : "salad"
                  }
                />
                <div className="meal-list__detail">
                  <div>
                    <Badge tone="neutral">{meal.meal_type}</Badge>
                    <span className="meal-list__date">
                      <CalendarDays size={14} />
                      {new Date(meal.eaten_at).toLocaleString([], {
                        dateStyle: "medium",
                        timeStyle: "short",
                        timeZone: timezone,
                      })}
                    </span>
                  </div>
                  <h3>{meal.items.map((item) => item.food_name).join(", ")}</h3>
                  <p>
                    {meal.items
                      .map(
                        (item) => `${Number(item.grams)} g ${item.food_name}`,
                      )
                      .join(" · ")}
                  </p>
                  {meal.notes && <p>{meal.notes}</p>}
                </div>
                <div className="meal-list__right">
                  <strong>
                    {Math.round(Number(meal.totals.kcal))} <small>kcal</small>
                  </strong>
                  <span>
                    P {Math.round(Number(meal.totals.protein_g))}g · C{" "}
                    {Math.round(Number(meal.totals.carbs_g))}g · F{" "}
                    {Math.round(Number(meal.totals.fat_g))}g
                  </span>
                  <div>
                    <button onClick={() => onEdit(meal)} aria-label="Edit meal">
                      <Pencil size={17} />
                    </button>
                    <button
                      onClick={() => onDelete(meal)}
                      aria-label="Delete meal"
                    >
                      <Trash2 size={17} />
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<Utensils size={26} />}
            title={
              meals.length ? "No matching meals" : "Your diary starts here"
            }
            text={
              meals.length
                ? "Try another search or filter."
                : "Log your first meal to start seeing your nutrition picture."
            }
            action={
              !meals.length && (
                <Button size="sm" icon={<Plus size={16} />} onClick={onAdd}>
                  Log a meal
                </Button>
              )
            }
          />
        )}
      </Card>
    </>
  );
}
