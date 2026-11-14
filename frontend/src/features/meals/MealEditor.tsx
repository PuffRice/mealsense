import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Camera,
  Check,
  ImagePlus,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  VideoOff,
  X,
} from "lucide-react";
import {
  Badge,
  Field,
  GlassButton,
  GlassModal,
  SelectField,
} from "../../design/ui";
import { modalMotionVariants } from "../../design/motion";
import { foodsApi, mealsApi, uploadMealImage } from "../../lib/api";
import { loadDraft, removeDraft, saveDraft } from "../../lib/offline";
import type {
  Candidate,
  Food,
  Meal,
  MealInput,
  VLMAnalysis,
} from "../../lib/types";

function localDateTime(date?: string) {
  const value = date ? new Date(date) : new Date();
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}

type FallbackNutrition = {
  portion_g: number;
  kcal_100g: string;
  protein_100g: string;
  carbs_100g: string;
  fat_100g: string;
};

const FCTB_FALLBACK_PER_100G: Record<string, FallbackNutrition> = {
  bakorkhani: { portion_g: 80, kcal_100g: "465.4", protein_100g: "8.8", carbs_100g: "63.2", fat_100g: "24.7" },
  bakarkhani: { portion_g: 80, kcal_100g: "465.4", protein_100g: "8.8", carbs_100g: "63.2", fat_100g: "24.7" },
  beguni: { portion_g: 100, kcal_100g: "272.5", protein_100g: "7.9", carbs_100g: "21.4", fat_100g: "17.3" },
  biriyani: { portion_g: 350, kcal_100g: "178.6", protein_100g: "9.8", carbs_100g: "16.4", fat_100g: "7.3" },
  biryani: { portion_g: 350, kcal_100g: "178.6", protein_100g: "9.8", carbs_100g: "16.4", fat_100g: "7.3" },
  chicken_biryani: { portion_g: 350, kcal_100g: "178.6", protein_100g: "9.8", carbs_100g: "16.4", fat_100g: "7.3" },
  mutton_biryani: { portion_g: 380, kcal_100g: "190.4", protein_100g: "10.6", carbs_100g: "15.5", fat_100g: "9.5" },
  kacchi: { portion_g: 380, kcal_100g: "190.4", protein_100g: "10.6", carbs_100g: "15.5", fat_100g: "9.5" },
  kacchi_biryani: { portion_g: 380, kcal_100g: "190.4", protein_100g: "10.6", carbs_100g: "15.5", fat_100g: "9.5" },
  chickpeas: { portion_g: 160, kcal_100g: "176.2", protein_100g: "6.6", carbs_100g: "19.7", fat_100g: "8.1" },
  chola: { portion_g: 160, kcal_100g: "176.2", protein_100g: "6.6", carbs_100g: "19.7", fat_100g: "8.1" },
  egg_omlete: { portion_g: 75, kcal_100g: "223.8", protein_100g: "11.3", carbs_100g: "2.6", fat_100g: "18.5" },
  egg_omelette: { portion_g: 75, kcal_100g: "223.8", protein_100g: "11.3", carbs_100g: "2.6", fat_100g: "18.5" },
  omelette: { portion_g: 75, kcal_100g: "223.8", protein_100g: "11.3", carbs_100g: "2.6", fat_100g: "18.5" },
  fuchka: { portion_g: 180, kcal_100g: "212.4", protein_100g: "5.2", carbs_100g: "28.9", fat_100g: "8.4" },
  haleem: { portion_g: 280, kcal_100g: "239.2", protein_100g: "14.0", carbs_100g: "14.5", fat_100g: "13.8" },
  hilsha_fish: { portion_g: 180, kcal_100g: "356.1", protein_100g: "19.5", carbs_100g: "2.7", fat_100g: "29.0" },
  hilsa_fish: { portion_g: 180, kcal_100g: "356.1", protein_100g: "19.5", carbs_100g: "2.7", fat_100g: "29.0" },
  lamb_curry: { portion_g: 200, kcal_100g: "215.0", protein_100g: "18.4", carbs_100g: "3.5", fat_100g: "14.2" },
  mutton_curry: { portion_g: 200, kcal_100g: "215.0", protein_100g: "18.4", carbs_100g: "3.5", fat_100g: "14.2" },
  beef_curry: { portion_g: 200, kcal_100g: "228.0", protein_100g: "19.2", carbs_100g: "3.2", fat_100g: "15.4" },
  chicken_curry: { portion_g: 200, kcal_100g: "172.0", protein_100g: "19.8", carbs_100g: "3.4", fat_100g: "8.8" },
  rice: { portion_g: 200, kcal_100g: "126.9", protein_100g: "2.7", carbs_100g: "28.1", fat_100g: "0.3" },
  potatoes: { portion_g: 150, kcal_100g: "71.7", protein_100g: "1.4", carbs_100g: "16.1", fat_100g: "0.1" },
  potato: { portion_g: 150, kcal_100g: "71.7", protein_100g: "1.4", carbs_100g: "16.1", fat_100g: "0.1" },
  saffron_milk: { portion_g: 200, kcal_100g: "97.0", protein_100g: "3.5", carbs_100g: "11.4", fat_100g: "4.1" },
  dal: { portion_g: 180, kcal_100g: "134.4", protein_100g: "9.7", carbs_100g: "22.3", fat_100g: "0.4" },
};

function lookupClientNutritionFallback(
  rawName?: string,
  modelLabel?: string,
): FallbackNutrition {
  const keys = [modelLabel, rawName]
    .filter(Boolean)
    .map((val) =>
      String(val)
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, ""),
    );
  for (const key of keys) {
    if (FCTB_FALLBACK_PER_100G[key]) return FCTB_FALLBACK_PER_100G[key];
    for (const [k, v] of Object.entries(FCTB_FALLBACK_PER_100G)) {
      if (key.includes(k) || k.includes(key)) return v;
    }
  }
  return {
    portion_g: 150,
    kcal_100g: "165.0",
    protein_100g: "8.5",
    carbs_100g: "20.0",
    fat_100g: "5.5",
  };
}
type Entry = {
  key: string;
  food_id: string;
  grams: number;
  serving_id?: number;
  recognition_result_id?: string;
};
export function MealEditor({
  meal,
  initialCameraOpen = false,
  userId,
  foods,
  onClose,
  onSaved,
  onFoodCreated,
}: {
  meal: Meal | null;
  initialCameraOpen?: boolean;
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
      serving_id: item.serving || undefined,
      recognition_result_id: item.recognition_result || undefined,
    })) || [],
  );
  const [query, setQuery] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null);
  const [imageId, setImageId] = useState<string | null>(meal?.image || null);
  const [custom, setCustom] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customPortionGrams, setCustomPortionGrams] = useState("100");
  const [customKcal, setCustomKcal] = useState("");
  const [customProtein, setCustomProtein] = useState("");
  const [customCarbs, setCustomCarbs] = useState("");
  const [customFat, setCustomFat] = useState("");
  const [customRecognitionResultId, setCustomRecognitionResultId] = useState<
    string | undefined
  >();
  const [vlmAnalysis, setVlmAnalysis] = useState<VLMAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [analyzingPhoto, setAnalyzingPhoto] = useState(false);
  const [error, setError] = useState("");
  const [photoNotice, setPhotoNotice] = useState("");
  const [suggestions, setSuggestions] = useState<Candidate[]>([]);
  const [operationId] = useState(crypto.randomUUID());
  const [draftReady, setDraftReady] = useState(false);

  // Camera state & refs
  const [cameraActive, setCameraActive] = useState(false);
  const [facingMode, setFacingMode] = useState<"environment" | "user">(
    "environment",
  );
  const [cameraError, setCameraError] = useState("");
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  }, []);

  const startCamera = useCallback(
    async (mode: "environment" | "user" = facingMode) => {
      setCameraError("");
      stopCamera();
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setCameraError(
          "Live camera is not available in this browser. Please upload a food image instead.",
        );
        return;
      }
      try {
        let stream: MediaStream;
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: {
              facingMode: { ideal: mode },
              width: { ideal: 1280 },
              height: { ideal: 960 },
            },
            audio: false,
          });
        } catch {
          stream = await navigator.mediaDevices.getUserMedia({
            video: true,
            audio: false,
          });
        }
        streamRef.current = stream;
        setCameraActive(true);
        requestAnimationFrame(() => {
          if (videoRef.current) {
            videoRef.current.srcObject = stream;
            void videoRef.current.play().catch(() => {});
          }
        });
      } catch {
        setCameraError(
          "Could not access camera. Check camera permissions or use Upload Food Image.",
        );
        setCameraActive(false);
      }
    },
    [facingMode, stopCamera],
  );

  useEffect(() => {
    if (initialCameraOpen) {
      void startCamera("environment");
    }
    return () => {
      stopCamera();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCameraOpen]);

  useEffect(() => {
    if (!photo) {
      setPhotoPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(photo);
    setPhotoPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  useEffect(() => {
    if (meal) return;
    let mounted = true;
    loadDraft()
      .then((draft) => {
        if (!mounted) return;
        if (draft?.userId === userId) {
          setKind(draft.kind);
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
    .filter((food) =>
      (food.name + " " + (food.name_bn || ""))
        .toLowerCase()
        .includes(query.toLowerCase()),
    )
    .slice(0, 8);

  const estimate = useMemo(
    () =>
      entries.reduce((sum, entry) => {
        const food = foods.find((item) => item.id === entry.food_id);
        return (
          sum +
          (food?.kcal_100g !== null && food?.kcal_100g !== undefined
            ? (Number(food.kcal_100g) * entry.grams) / 100
            : 0)
        );
      }, 0),
    [entries, foods],
  );

  const hasPendingNutrition = entries.some((entry) => {
    const food = foods.find((item) => item.id === entry.food_id);
    return food?.kcal_100g === null || food?.kcal_100g === undefined;
  });

  function addFood(food: Food, recognitionResultId?: string, grams = 100) {
    setEntries((current) => [
      ...current,
      {
        key: crypto.randomUUID(),
        food_id: food.id,
        grams: grams > 0 ? Math.round(grams) : 100,
        recognition_result_id: recognitionResultId,
      },
    ]);
    setQuery("");
  }

  function populateFormWithAnalysis(
    analysis: VLMAnalysis | undefined | null,
    candidate?: Candidate,
  ) {
    setQuery("");
    setCustom(true);
    setCustomRecognitionResultId(candidate?.result_id);

    const fallback = lookupClientNutritionFallback(
      analysis?.food_name || candidate?.name,
      analysis?.food_class || candidate?.model_label,
    );

    if (
      analysis &&
      analysis.nutrition &&
      analysis.nutrition.calories_kcal !== null &&
      analysis.nutrition.calories_kcal !== undefined
    ) {
      setVlmAnalysis(analysis);
      const portionWeight =
        analysis.portion?.estimated_weight_g &&
        analysis.portion.estimated_weight_g > 0
          ? analysis.portion.estimated_weight_g
          : fallback.portion_g;
      const roundedPortion = Math.max(1, Math.round(portionWeight));
      setCustomName(analysis.food_name || candidate?.name || "");
      setCustomPortionGrams(String(roundedPortion));

      const nut = analysis.nutrition;
      const toPer100g = (
        val: number | null | undefined,
        fallbackVal: string,
      ) => {
        if (val === null || val === undefined || Number.isNaN(Number(val)))
          return fallbackVal;
        return String(
          Math.max(
            0,
            Math.round(((Number(val) / portionWeight) * 100) * 10) / 10,
          ),
        );
      };
      setCustomKcal(toPer100g(nut?.calories_kcal, fallback.kcal_100g));
      setCustomProtein(toPer100g(nut?.protein_g, fallback.protein_100g));
      setCustomCarbs(toPer100g(nut?.carbohydrates_g, fallback.carbs_100g));
      setCustomFat(toPer100g(nut?.fat_g, fallback.fat_100g));
    } else if (candidate) {
      setVlmAnalysis(analysis || null);
      setCustomName(candidate.name);
      const existingFood = candidate.food_id
        ? foods.find((item) => item.id === candidate.food_id)
        : undefined;
      if (existingFood && existingFood.kcal_100g !== null) {
        setCustomPortionGrams("100");
        setCustomKcal(String(existingFood.kcal_100g));
        setCustomProtein(String(existingFood.protein_100g ?? "0"));
        setCustomCarbs(String(existingFood.carbs_100g ?? "0"));
        setCustomFat(String(existingFood.fat_100g ?? "0"));
      } else {
        setCustomPortionGrams(String(fallback.portion_g));
        setCustomKcal(fallback.kcal_100g);
        setCustomProtein(fallback.protein_100g);
        setCustomCarbs(fallback.carbs_100g);
        setCustomFat(fallback.fat_100g);
      }
    }

    requestAnimationFrame(() => {
      document.getElementById("custom-food-form")?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    });
  }

  async function saveCustomFoodToEntries(): Promise<Entry | null> {
    if (
      !customName.trim() ||
      [customKcal, customProtein, customCarbs, customFat].some(
        (value) => value === "" || Number(value) < 0,
      )
    ) {
      setError("Enter a food name and all per 100 g nutrition values.");
      return null;
    }
    const portionGramsNum = Math.max(1, Number(customPortionGrams) || 100);
    const food = await foodsApi.create({
      name: customName.trim(),
      category: "My foods",
      kcal_100g: customKcal,
      protein_100g: customProtein,
      carbs_100g: customCarbs,
      fat_100g: customFat,
      source_ref: vlmAnalysis
        ? "DINOv3 + Qwen-VL / FCTB estimate (user reviewed)"
        : "",
    } as Parameters<typeof foodsApi.create>[0]);
    onFoodCreated(food);
    const newEntry: Entry = {
      key: crypto.randomUUID(),
      food_id: food.id,
      grams: Math.round(portionGramsNum),
      recognition_result_id: customRecognitionResultId,
    };
    setEntries((current) => [...current, newEntry]);
    setCustom(false);
    setCustomName("");
    setCustomKcal("");
    setCustomProtein("");
    setCustomCarbs("");
    setCustomFat("");
    setCustomPortionGrams("100");
    setCustomRecognitionResultId(undefined);
    return newEntry;
  }

  async function createFood() {
    setError("");
    setBusy(true);
    try {
      await saveCustomFoodToEntries();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not add food.");
    } finally {
      setBusy(false);
    }
  }

  async function pickPhoto(file: File | null) {
    stopCamera();
    setSuggestions([]);
    setPhotoNotice("");
    setVlmAnalysis(null);
    setPhoto(file);
    if (file)
      setEntries((current) =>
        current.map((entry) => ({
          ...entry,
          recognition_result_id: undefined,
        })),
      );
    if (!file) return;
    if (!navigator.onLine) {
      setError(
        "You are offline. Photos upload when online; add food manually now.",
      );
      return;
    }
    setBusy(true);
    setAnalyzingPhoto(true);
    setError("");
    try {
      const result = await uploadMealImage(file);
      setImageId(result.image_id);
      setPhotoNotice(result.message);
      const candidateList =
        result.status === "completed" ? result.candidates : [];
      setSuggestions(candidateList);
      const topCandidate = candidateList[0];
      const analysis = result.analysis || topCandidate?.analysis || null;
      if (analysis || topCandidate) {
        populateFormWithAnalysis(analysis, topCandidate);
      }
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not upload photo.",
      );
    } finally {
      setBusy(false);
      setAnalyzingPhoto(false);
    }
  }

  function capturePhotoFromVideo() {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) {
      setCameraError("Camera stream is still initializing. Try again in a moment.");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setCameraError("Could not capture image frame.");
          return;
        }
        const capturedFile = new File([blob], `camera_meal_${Date.now()}.jpg`, {
          type: "image/jpeg",
        });
        void pickPhoto(capturedFile);
      },
      "image/jpeg",
      0.92,
    );
  }

  function toggleFacingMode() {
    const nextMode = facingMode === "environment" ? "user" : "environment";
    setFacingMode(nextMode);
    void startCamera(nextMode);
  }

  function applySuggestion(candidate: Candidate) {
    // Prefer the candidate's own analysis; always open & fill the Add Food form
    // so the user can review/edit the nutrition values before saving.
    const analysis =
      candidate.analysis ||
      (vlmAnalysis &&
      (vlmAnalysis.food_class === candidate.model_label ||
        vlmAnalysis.canonical_catalog_name === candidate.name ||
        vlmAnalysis.food_name === candidate.name)
        ? vlmAnalysis
        : undefined);
    populateFormWithAnalysis(analysis, candidate);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (!navigator.onLine) {
      setError(
        "Draft saved on this device. Open it again and save when online.",
      );
      return;
    }
    setBusy(true);
    try {
      let currentEntries = [...entries];
      // If user has a populated Add Food form open and clicks "Save meal" directly,
      // save the custom food first and include it in the meal items.
      if (
        custom &&
        customName.trim() &&
        [customKcal, customProtein, customCarbs, customFat].every(
          (val) => val !== "" && Number(val) >= 0,
        )
      ) {
        const addedEntry = await saveCustomFoodToEntries();
        if (addedEntry) {
          currentEntries = [...currentEntries, addedEntry];
        } else {
          setBusy(false);
          return;
        }
      }

      if (!currentEntries.length) {
        setError("Add at least one food or scan a food photo first.");
        setBusy(false);
        return;
      }

      const data: MealInput = {
        eaten_at: new Date(when).toISOString(),
        meal_type: kind,
        notes,
        image_id: imageId,
        items: currentEntries.map(
          ({ food_id, grams, serving_id, recognition_result_id }) => ({
            food_id,
            grams,
            serving_id,
            recognition_result_id,
          }),
        ),
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

  const customPortionTotalKcal = useMemo(() => {
    const kcal100 = Number(customKcal);
    const grams = Number(customPortionGrams);
    if (!customKcal || Number.isNaN(kcal100) || Number.isNaN(grams) || grams <= 0)
      return null;
    return Math.round((kcal100 * grams) / 100);
  }, [customKcal, customPortionGrams]);

  return (
    <GlassModal titleId="meal-editor-title" onClose={onClose}>
      <div className="modal__head">
        <div>
          <span className="eyebrow">YOUR FOOD DIARY</span>
          <h2 id="meal-editor-title">
            {meal ? "Edit your meal" : "Scan or log a meal"}
          </h2>
          <p>
            Capture a food photo with the camera or upload an image — DINOv3 &
            Qwen-VL will predict the dish and pre-fill its nutrition for you.
          </p>
        </div>
        <button
          type="button"
          className="icon-button"
          onClick={() => {
            stopCamera();
            onClose();
          }}
          aria-label="Close"
        >
          <X size={18} />
        </button>
      </div>
      <form onSubmit={save} className="modal__body">
        <div className="editor-section scanner-section">
          <div className="editor-section__heading">
            <h3>AI Food Scanner (DINOv3 + VLM)</h3>
            <Badge tone="green">Camera & Upload</Badge>
          </div>

          <div className="scanner-actions">
            <GlassButton
              type="button"
              size="sm"
              variant={cameraActive ? "secondary" : "primary"}
              icon={
                cameraActive ? <VideoOff size={16} /> : <Camera size={16} />
              }
              disabled={busy}
              onClick={() => {
                if (cameraActive) stopCamera();
                else void startCamera();
              }}
            >
              {cameraActive ? "Close camera" : "Turn on camera"}
            </GlassButton>

            <GlassButton
              type="button"
              size="sm"
              variant="secondary"
              icon={<ImagePlus size={16} />}
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
            >
              Upload food image
            </GlassButton>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="sr-only-input"
              onChange={(event) => {
                void pickPhoto(event.target.files?.[0] ?? null);
                event.target.value = "";
              }}
            />
          </div>

          {cameraError && (
            <div className="scanner-fallback">
              <p className="editor-note">{cameraError}</p>
              <label className="photo-upload">
                <Camera size={18} />
                <span>Take photo or choose image from device</span>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  capture="environment"
                  onChange={(event) =>
                    void pickPhoto(event.target.files?.[0] ?? null)
                  }
                />
              </label>
            </div>
          )}

          {cameraActive && (
            <div className="camera-viewport">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="camera-viewport__video"
              />
              <div className="camera-viewport__controls">
                <GlassButton
                  type="button"
                  size="sm"
                  variant="secondary"
                  icon={<RefreshCw size={15} />}
                  onClick={toggleFacingMode}
                >
                  Flip camera
                </GlassButton>
                <GlassButton
                  type="button"
                  size="md"
                  variant="primary"
                  icon={<Camera size={17} />}
                  onClick={capturePhotoFromVideo}
                >
                  Capture food photo
                </GlassButton>
              </div>
            </div>
          )}

          {photoPreviewUrl && !cameraActive && (
            <div className="scanner-preview">
              <img
                src={photoPreviewUrl}
                alt="Selected food"
                className="scanner-preview__img"
              />
              <div className="scanner-preview__meta">
                <strong>{photo?.name || "Captured food photo"}</strong>
                {analyzingPhoto ? (
                  <span className="scanner-preview__status">
                    <Sparkles size={14} className="doctor-spin" /> Running
                    DINOv3 classification & VLM nutrition analysis...
                  </span>
                ) : (
                  <small>{photoNotice || "Photo ready"}</small>
                )}
              </div>
            </div>
          )}

          {suggestions.length > 0 && (
            <div
              className="suggestion-row"
              aria-label="Food suggestions from your photo"
            >
              <span className="suggestion-row__label">
                DINOv3 predictions:
              </span>
              {suggestions.map((item) => (
                <button
                  type="button"
                  key={item.name}
                  className="suggestion-chip"
                  onClick={() => applySuggestion(item)}
                >
                  {item.name}
                  <small>
                    {Math.round(item.confidence * 100)}% · Fill form
                  </small>
                </button>
              ))}
            </div>
          )}
        </div>

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
          <div className="food-search glass-input-shell">
            <Search size={17} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search for food to add..."
              aria-label="Search foods"
            />
          </div>
          <AnimatePresence>
            {query && (
              <motion.div
                variants={modalMotionVariants}
                initial="initial"
                animate="animate"
                exit="exit"
                className="food-results"
              >
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
                        {food.kcal_100g === null
                          ? "Nutrition pending"
                          : `${Math.round(Number(food.kcal_100g))} kcal / 100 g`}
                      </small>
                    </span>
                    <Plus size={17} />
                  </button>
                ))}
                {filtered.length === 0 && (
                  <p>No matching food. Add your own below.</p>
                )}
              </motion.div>
            )}
          </AnimatePresence>
          {entries.map((entry) => {
            const food = foods.find((item) => item.id === entry.food_id);
            return (
              <div className="editor-item" key={entry.key}>
                <div className="editor-item__mark" aria-hidden="true">
                  •
                </div>
                <div>
                  <strong>{food?.name || "Unknown food"}</strong>
                  <small>
                    {food?.source || "Reference"} ·{" "}
                    {food?.kcal_100g === null
                      ? "Nutrition pending"
                      : `~${Math.round((Number(food?.kcal_100g || 0) * entry.grams) / 100)} kcal`}
                  </small>
                  {!!food?.servings?.length && (
                    <select
                      className="editor-item__serving"
                      aria-label={`Serving for ${food.name}`}
                      value={entry.serving_id || ""}
                      onChange={(event) => {
                        const serving = food.servings?.find(
                          (option) => option.id === Number(event.target.value),
                        );
                        setEntries(
                          entries.map((item) =>
                            item.key === entry.key
                              ? {
                                  ...item,
                                  serving_id: serving?.id,
                                  grams: serving
                                    ? Number(serving.weight_g)
                                    : item.grams,
                                }
                              : item,
                          ),
                        );
                      }}
                    >
                      <option value="">Custom weight in grams</option>
                      {food.servings.map((serving) => (
                        <option key={serving.id} value={serving.id}>
                          {serving.name} · {serving.weight_g} g
                          {serving.is_approximate ? " approx." : ""}
                        </option>
                      ))}
                    </select>
                  )}
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
                            ? {
                                ...item,
                                grams: Number(event.target.value),
                                serving_id: undefined,
                              }
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
                    setEntries(entries.filter((item) => item.key !== entry.key))
                  }
                >
                  <Trash2 size={16} />
                </button>
              </div>
            );
          })}
          <button
            type="button"
            className="text-action"
            onClick={() => {
              setCustom(!custom);
              setCustomRecognitionResultId(undefined);
            }}
          >
            <Plus size={16} />{" "}
            {custom ? "Hide add food form" : "Add a food / AI nutrition form"}
          </button>
          {custom && (
            <div className="custom-food" id="custom-food-form">
              {vlmAnalysis && (
                <div className="vlm-banner">
                  <div className="vlm-banner__head">
                    <Sparkles size={15} />
                    <strong>
                      AI Predicted: {vlmAnalysis.food_name}
                    </strong>
                    {vlmAnalysis.classification && (
                      <Badge tone="green">
                        {Math.round(
                          vlmAnalysis.classification.confidence * 100,
                        )}
                        % match
                      </Badge>
                    )}
                  </div>
                  {vlmAnalysis.portion?.portion_description && (
                    <p className="vlm-banner__sub">
                      Portion estimate:{" "}
                      <strong>
                        {vlmAnalysis.portion.portion_description} (~
                        {Math.round(
                          vlmAnalysis.portion.estimated_weight_g || 100,
                        )}{" "}
                        g)
                      </strong>
                      {vlmAnalysis.nutrition?.calories_kcal != null && (
                        <>
                          {" "}
                          · Total portion:{" "}
                          <strong>
                            ~{Math.round(vlmAnalysis.nutrition.calories_kcal)}{" "}
                            kcal
                          </strong>{" "}
                          (P {vlmAnalysis.nutrition.protein_g ?? 0}g · C{" "}
                          {vlmAnalysis.nutrition.carbohydrates_g ?? 0}g · F{" "}
                          {vlmAnalysis.nutrition.fat_g ?? 0}g)
                        </>
                      )}
                    </p>
                  )}
                  {vlmAnalysis.ingredients &&
                    vlmAnalysis.ingredients.length > 0 && (
                      <div className="vlm-banner__ingredients">
                        <span>Detected ingredients: </span>
                        {vlmAnalysis.ingredients
                          .slice(0, 6)
                          .map((ing) =>
                            ing.estimated_weight_g
                              ? `${ing.name} (${Math.round(ing.estimated_weight_g)}g)`
                              : ing.name,
                          )
                          .join(", ")}
                      </div>
                    )}
                </div>
              )}

              <div className="custom-food__grid">
                <Field
                  id="custom-food-name"
                  label="Food name"
                  value={customName}
                  onChange={(event) => setCustomName(event.target.value)}
                  placeholder="e.g. Chicken Biryani"
                />
                <Field
                  label="Portion weight (g)"
                  type="number"
                  min="1"
                  max="10000"
                  value={customPortionGrams}
                  onChange={(event) =>
                    setCustomPortionGrams(event.target.value)
                  }
                />
              </div>
              <div className="custom-food__grid">
                <Field
                  label="Calories / 100 g"
                  type="number"
                  min="0"
                  step="any"
                  value={customKcal}
                  onChange={(event) => setCustomKcal(event.target.value)}
                />
                <Field
                  label="Protein (g) / 100 g"
                  type="number"
                  min="0"
                  step="any"
                  value={customProtein}
                  onChange={(event) => setCustomProtein(event.target.value)}
                />
                <Field
                  label="Carbs (g) / 100 g"
                  type="number"
                  min="0"
                  step="any"
                  value={customCarbs}
                  onChange={(event) => setCustomCarbs(event.target.value)}
                />
                <Field
                  label="Fat (g) / 100 g"
                  type="number"
                  min="0"
                  step="any"
                  value={customFat}
                  onChange={(event) => setCustomFat(event.target.value)}
                />
              </div>
              <p>
                {vlmAnalysis
                  ? `Pre-filled by DINOv3 + Qwen-VL (grounded with FCTB per 100 g).${customPortionTotalKcal !== null ? ` At ${customPortionGrams} g, this portion is ~${customPortionTotalKcal} kcal.` : ""} You can edit any value before saving.`
                  : "Use values from a label or trusted reference. You can edit any value before saving."}
              </p>
              <GlassButton
                type="button"
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={createFood}
              >
                Save food & add to meal
              </GlassButton>
            </div>
          )}
        </div>
        <label className="field">
          <span className="field__label">Notes (optional)</span>
          <textarea
            className="field__input glass-input"
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
            {hasPendingNutrition ? (
              <strong>Nutrition pending</strong>
            ) : (
              <>
                Estimated total{" "}
                <strong>
                  ~
                  {Math.round(
                    estimate +
                      (entries.length === 0 && customPortionTotalKcal !== null
                        ? customPortionTotalKcal
                        : 0),
                  )}{" "}
                  kcal
                </strong>
              </>
            )}
          </span>
          <GlassButton type="submit" disabled={busy} icon={<Check size={17} />}>
            {busy ? "Saving..." : meal ? "Save changes" : "Save meal"}
          </GlassButton>
        </div>
      </form>
    </GlassModal>
  );
}
