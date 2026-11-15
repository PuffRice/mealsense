import type { Daily, Food, Meal, User } from "./types";

export type Snapshot = {
  user: User;
  meals: Meal[];
  foods: Food[];
  daily: Daily;
  weekly: Daily[];
  savedAt: string;
};
export type MealDraft = {
  userId: string;
  kind: Meal["meal_type"];
  when: string;
  notes: string;
  entries: {
    key: string;
    food_id: string;
    grams: number;
    /** How many pieces/servings of the food; defaults to 1 for older drafts. */
    count?: number;
    /** Weight of ONE piece/serving in grams; derived from grams if absent. */
    unit_grams?: number;
    serving_id?: number;
    recognition_result_id?: string;
  }[];
};

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("mealsense-local", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("data");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function read<T>(key: string): Promise<T | null> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("data", "readonly");
    const request = tx.objectStore("data").get(key);
    request.onsuccess = () => resolve((request.result as T) || null);
    request.onerror = () => reject(request.error);
    tx.oncomplete = () => db.close();
  });
}
async function write(key: string, value: unknown) {
  const db = await database();
  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction("data", "readwrite");
    tx.objectStore("data").put(value, key);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => reject(tx.error);
  });
}
export const loadSnapshot = () => read<Snapshot>("snapshot");
export const saveSnapshot = (snapshot: Snapshot) => write("snapshot", snapshot);
export const loadDraft = () => read<MealDraft>("draft");
export const saveDraft = (draft: MealDraft) => write("draft", draft);
export async function removeDraft() {
  const db = await database();
  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction("data", "readwrite");
    tx.objectStore("data").delete("draft");
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => reject(tx.error);
  });
}
export async function clearLocalData() {
  const db = await database();
  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction("data", "readwrite");
    tx.objectStore("data").clear();
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => reject(tx.error);
  });
}
