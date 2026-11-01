import { useEffect, useMemo, useState } from "react";
import { Camera, Check, Plus, Search, Trash2, X } from "lucide-react";
import { Badge, Button, Field, SelectField } from "../../design/ui";
import { foodsApi, mealsApi, uploadMealImage } from "../../lib/api";
import { loadDraft, removeDraft, saveDraft } from "../../lib/offline";
import type { Candidate, Food, Meal, MealInput } from "../../lib/types";

function localDateTime(date?: string) {
  const value = date ? new Date(date) : new Date();
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
type Entry = { key: string; food_id: string; grams: number };
export function MealEditor({
  meal,
  userId,
  foods,
  onClose,
  onSaved,
  onFoodCreated,
}: {
  meal: Meal | null;
  userId: string;
  foods: Food[];
  onClose: () => void;
  onSaved: () => Promise<void>;
  onFoodCreated: (food: Food) => void;
}) {
  const [kind, setKind] = useState<Meal["meal_type"]>(
    meal?.meal_type || "lunch",
  );
  const [when, setWhen] = useState(localDateTime(meal?.eaten_at));
  const [notes, setNotes] = useState(meal?.notes || "");
  const [entries, setEntries] = useState<Entry[]>(
    meal?.items.map((item) => ({
      key: item.id,
      food_id: item.food,
      grams: Number(item.grams),
    })) || [],
  );
  const [query, setQuery] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [imageId, setImageId] = useState<string | null>(meal?.image || null);
  const [custom, setCustom] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customKcal, setCustomKcal] = useState("");
  const [customProtein, setCustomProtein] = useState("");
  const [customCarbs, setCustomCarbs] = useState("");
  const [customFat, setCustomFat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [photoNotice, setPhotoNotice] = useState("");
  const [suggestions, setSuggestions] = useState<Candidate[]>([]);
  const [operationId] = useState(crypto.randomUUID());
  const [draftReady, setDraftReady] = useState(false);
  useEffect(() => {
    if (meal) return;
    let mounted = true;
    loadDraft()
      .then((draft) => {
        if (!mounted) return;
        if (draft?.userId === userId) {
          setKind(draft.kind);
          setWhen(draft.when);
          setNotes(draft.notes);
          setEntries(draft.entries);
        }
        setDraftReady(true);
      })
      .catch(() => setDraftReady(true));
    return () => {
      mounted = false;
    };
  }, [meal, userId]);
  useEffect(() => {
    if (!meal && draftReady)
      void saveDraft({ userId, kind, when, notes, entries }).catch(() => {});
  }, [meal, draftReady, userId, kind, when, notes, entries]);
  const filtered = foods
    .filter((food) => food.name.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 8);
  const estimate = useMemo(
    () =>
      entries.reduce((sum, entry) => {
        const food = foods.find((item) => item.id === entry.food_id);
        return sum + (food ? (Number(food.kcal_100g) * entry.grams) / 100 : 0);
      }, 0),
    [entries, foods],
  );
  function addFood(food: Food) {
    setEntries([
      ...entries,
      { key: crypto.randomUUID(), food_id: food.id, grams: 100 },
    ]);
    setQuery("");
  }
  async function createFood() {
    setError("");
    if (
      !customName.trim() ||
      [customKcal, customProtein, customCarbs, customFat].some(
        (value) => !value || Number(value) < 0,
      )
    ) {
      setError("Enter a name and all per 100 g values.");
      return;
    }
    setBusy(true);
    try {
      const food = await foodsApi.create({
        name: customName.trim(),
        category: "My foods",
        kcal_100g: customKcal,
        protein_100g: customProtein,
        carbs_100g: customCarbs,
        fat_100g: customFat,
        source_ref: "",
      } as Parameters<typeof foodsApi.create>[0]);
      onFoodCreated(food);
      addFood(food);
      setCustom(false);
      setCustomName("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not add food.");
    } finally {
      setBusy(false);
    }
  }
  async function pickPhoto(file: File | null) {
    setSuggestions([]);
    setPhotoNotice("");
    setPhoto(file);
    if (!file) return;
    if (!navigator.onLine) {
      setError(
        "You are offline. Photos upload when online; add food manually now.",
      );
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await uploadMealImage(file);
      setImageId(result.image_id);
      setPhotoNotice(result.message);
      setSuggestions(result.status === "completed" ? result.candidates : []);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not upload photo.",
      );
    } finally {
      setBusy(false);
    }
  }
  function applySuggestion(candidate: Candidate) {
    const food = candidate.food_id
      ? foods.find((item) => item.id === candidate.food_id)
      : undefined;
    if (food) addFood(food);
    else setQuery(candidate.name);
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (!entries.length) {
      setError("Add at least one food.");
      return;
    }
    if (!navigator.onLine) {
      setError(
        "Draft saved on this device. Open it again and save when online.",
      );
      return;
    }
    setBusy(true);
    try {
      const data: MealInput = {
        eaten_at: new Date(when).toISOString(),
        meal_type: kind,
        notes,
        image_id: imageId,
        items: entries.map(({ food_id, grams }) => ({ food_id, grams })),
        operation_id: operationId,
      };
      if (meal)
        await mealsApi.update(meal.id, { ...data, version: meal.version });
      else await mealsApi.create(data);
      setDraftReady(false);
      if (!meal) await removeDraft().catch(() => {});
      await onSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save meal.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="meal-editor-title"
      >
        <div className="modal__head">
          <div>
            <span className="eyebrow">YOUR FOOD DIARY</span>
            <h2 id="meal-editor-title">
              {meal ? "Edit your meal" : "Log a meal"}
            </h2>
            <p>Tell us what you ate. You can always update it later.</p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>
        <form onSubmit={save} className="modal__body">
          <div className="editor-two">
            <SelectField
              label="Meal type"
              value={kind}
              onChange={(value) => setKind(value as Meal["meal_type"])}
            >
              <option value="breakfast">Breakfast</option>
              <option value="lunch">Lunch</option>
              <option value="dinner">Dinner</option>
              <option value="snack">Snack</option>
            </SelectField>
            <Field
              label="When did you eat? (device time)"
              type="datetime-local"
              value={when}
              onChange={(event) => setWhen(event.target.value)}
              required
            />
          </div>
          <div className="editor-section">
            <div className="editor-section__heading">
              <h3>Foods you ate</h3>
              <Badge tone="neutral">Per 100 g references</Badge>
            </div>
            <div className="food-search">
              <Search size={18} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search for food to add..."
                aria-label="Search foods"
              />
            </div>
            {query && (
              <div className="food-results">
                {filtered.map((food) => (
                  <button
                    type="button"
                    key={food.id}
                    onClick={() => addFood(food)}
                  >
                    <span>
                      {food.name}
                      <small>
                        {food.is_sample ? "Sample estimate" : food.source} ·{" "}
                        {Math.round(Number(food.kcal_100g))} kcal / 100 g
                      </small>
                    </span>
                    <Plus size={18} />
                  </button>
                ))}
                {filtered.length === 0 && (
                  <p>No matching food. Add your own below.</p>
                )}
              </div>
            )}
            {entries.map((entry) => {
              const food = foods.find((item) => item.id === entry.food_id);
              return (
                <div className="editor-item" key={entry.key}>
                  <div className="editor-item__mark">✳</div>
                  <div>
                    <strong>{food?.name || "Unknown food"}</strong>
                    <small>
                      {food?.source || "Reference"} · ~
                      {Math.round(
                        (Number(food?.kcal_100g || 0) * entry.grams) / 100,
                      )}{" "}
                      kcal
                    </small>
                  </div>
                  <div className="editor-item__amount">
                    <input
                      type="number"
                      min="1"
                      max="10000"
                      value={entry.grams}
                      onChange={(event) =>
                        setEntries(
                          entries.map((item) =>
                            item.key === entry.key
                              ? { ...item, grams: Number(event.target.value) }
                              : item,
                          ),
                        )
                      }
                      aria-label={`Grams of ${food?.name}`}
                    />
                    <span>g</span>
                  </div>
                  <button
                    type="button"
                    aria-label={`Remove ${food?.name}`}
                    onClick={() =>
                      setEntries(
                        entries.filter((item) => item.key !== entry.key),
                      )
                    }
                  >
                    <Trash2 size={17} />
                  </button>
                </div>
              );
            })}
            <button
              type="button"
              className="text-action"
              onClick={() => setCustom(!custom)}
            >
              <Plus size={17} />{" "}
              {custom ? "Hide custom food" : "Add a food not listed"}
            </button>
            {custom && (
              <div className="custom-food">
                <Field
                  label="Food name"
                  value={customName}
                  onChange={(event) => setCustomName(event.target.value)}
                  placeholder="e.g. Homemade dal"
                />
                <div className="custom-food__grid">
                  <Field
                    label="Calories / 100 g"
                    type="number"
                    min="0"
                    value={customKcal}
                    onChange={(event) => setCustomKcal(event.target.value)}
                  />
                  <Field
                    label="Protein / 100 g"
                    type="number"
                    min="0"
                    value={customProtein}
                    onChange={(event) => setCustomProtein(event.target.value)}
                  />
                  <Field
                    label="Carbs / 100 g"
                    type="number"
                    min="0"
                    value={customCarbs}
                    onChange={(event) => setCustomCarbs(event.target.value)}
                  />
                  <Field
                    label="Fat / 100 g"
                    type="number"
                    min="0"
                    value={customFat}
                    onChange={(event) => setCustomFat(event.target.value)}
                  />
                </div>
                <p>
                  Use values from a label or trusted reference. These values are
                  supplied by you.
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={busy}
                  onClick={createFood}
                >
                  Save custom food
                </Button>
              </div>
            )}
          </div>
          <div className="editor-section">
            <h3>Photo (optional)</h3>
            <label className="photo-upload">
              <Camera size={20} />
              <span>{photo ? photo.name : "Choose a meal photo"}</span>
              <small>JPEG, PNG or WebP · up to 8 MB</small>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(event) =>
                  void pickPhoto(event.target.files?.[0] ?? null)
                }
              />
            </label>
            <p className="editor-note">
              Your photo is analyzed only to suggest foods. Suggestions are
              approximate; you pick the food and serving size yourself. Text
              drafts save locally; photos do not.
            </p>
            {suggestions.length > 0 && (
              <div
                className="suggestion-row"
                aria-label="Food suggestions from your photo"
              >
                <span className="suggestion-row__label">
                  Seen in your photo?
                </span>
                {suggestions.map((item) => (
                  <button
                    type="button"
                    key={item.name}
                    className="suggestion-chip"
                    onClick={() => applySuggestion(item)}
                  >
                    {item.name}
                    {item.category && <small>{item.category}</small>}
                  </button>
                ))}
              </div>
            )}
            {photoNotice && <p className="editor-note">{photoNotice}</p>}
          </div>
          <label className="field">
            <span className="field__label">Notes (optional)</span>
            <textarea
              className="field__input"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Anything you want to remember?"
              rows={2}
            />
          </label>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          <div className="modal__foot">
            <span>
              Estimated total <strong>~{Math.round(estimate)} kcal</strong>
            </span>
            <Button type="submit" disabled={busy} icon={<Check size={18} />}>
              {busy ? "Saving..." : meal ? "Save changes" : "Save meal"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
