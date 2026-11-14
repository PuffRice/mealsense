"""Stable names and search aliases for labels emitted by BanglaFoodNet."""

MODEL_CLASS_LABELS = {
    'bakorkhani': ('Bakarkhani', 'bakorkhani'),
    'beguni': ('Beguni',),
    'biriyani': ('Biryani', 'biriyani', 'biriani'),
    'chickpeas': ('Chickpeas', 'chola bhuna', 'chana'),
    'egg_omlete': ('Egg omelette', 'egg omelet', 'dim bhaji'),
    'fuchka': ('Fuchka', 'phuchka'),
    'haleem': ('Haleem', 'halim'),
    'hilsha_fish': ('Hilsa fish', 'hilsha fish', 'ilish fish'),
    'kacchi': ('Kacchi Biryani', 'kacchi', 'mutton kacchi biryani', 'biryani'),
    'kabab': ('Kebab', 'kabab'),
    'kacha_golla': ('Kacha golla', 'kacha golla'),
    'kala_bhuna': ('Kala bhuna', 'kala bhuna'),
    'khichuri': ('Khichuri', 'khichdi'),
    'mashed_potato': ('Mashed potato', 'aloo bhorta', 'alu bhorta'),
    'morog_polao': ('Morog polao', 'morog pulao'),
    'nehari': ('Nihari', 'nehari'),
    'porota': ('Paratha', 'porota', 'parota'),
    'roshgolla': ('Rasgulla', 'roshgolla', 'rosogolla'),
    'roshmalai': ('Ras malai', 'roshmalai', 'rasmalai'),
    'yogurt': ('Yogurt', 'yoghurt', 'doi'),
}


def model_display_name(model_label):
    values = MODEL_CLASS_LABELS.get(model_label)
    return values[0] if values else model_label.replace('_', ' ').capitalize()


def model_search_names(model_label, display_name):
    return (display_name, model_label.replace('_', ' '), *MODEL_CLASS_LABELS.get(model_label, ()))
