from django.core.validators import MinValueValidator
from django.db import migrations, models


SOURCE = 'BanglaFoodNet class catalog; nutrition pending'
SOURCE_REF = 'backend/model_artifacts.md'

# Canonical display name, Bengali name, category, search aliases.
FOODS = (
    ('Bakarkhani', 'বাকরখানি', 'Bread', ('bakorkhani',)),
    ('Beguni', 'বেগুনি', 'Snack', ()),
    ('Biryani', 'বিরিয়ানি', 'Rice dish', ('biriyani', 'biriani')),
    ('Chickpeas', 'ছোলা', 'Legume dish', ('chola bhuna', 'chana')),
    ('Egg omelette', 'ডিম ভাজি', 'Egg dish', ('egg omlete', 'egg omelet', 'dim bhaji')),
    ('Fuchka', 'ফুচকা', 'Snack', ('phuchka', 'pani puri')),
    ('Haleem', 'হালিম', 'Stew', ('halim',)),
    ('Hilsa fish', 'ইলিশ মাছ', 'Fish dish', ('hilsha fish', 'ilish fish')),
    ('Kebab', 'কাবাব', 'Meat dish', ('kabab',)),
    ('Kacha golla', 'কাঁচাগোল্লা', 'Sweet', ('kacha_golla',)),
    ('Kala bhuna', 'কালা ভুনা', 'Meat dish', ('kala_bhuna',)),
    ('Khichuri', 'খিচুড়ি', 'Rice dish', ('khichdi',)),
    ('Mashed potato', 'আলু ভর্তা', 'Vegetable dish', ('mashed_potato', 'aloo bhorta', 'alu bhorta')),
    ('Morog polao', 'মোরগ পোলাও', 'Rice dish', ('morog_polao', 'morog pulao')),
    ('Nihari', 'নেহারি', 'Meat dish', ('nehari',)),
    ('Paratha', 'পরোটা', 'Bread', ('porota', 'parota')),
    ('Rasgulla', 'রসগোল্লা', 'Sweet', ('roshgolla', 'rosogolla')),
    ('Ras malai', 'রসমালাই', 'Sweet', ('roshmalai', 'rasmalai')),
    ('Yogurt', 'দই', 'Dairy', ('yoghurt', 'doi')),
)


def seed_model_foods(apps, schema_editor):
    Food = apps.get_model('core', 'Food')
    FoodAlias = apps.get_model('core', 'FoodAlias')
    for name, name_bn, category, aliases in FOODS:
        food, _ = Food.objects.get_or_create(
            created_by=None,
            name=name,
            defaults={
                'name_bn': name_bn,
                'category': category,
                'source': SOURCE,
                'source_ref': SOURCE_REF,
                'is_active': True,
                'is_verified': False,
            },
        )
        for alias in aliases:
            FoodAlias.objects.get_or_create(
                food=food, alias=alias, language='en', region='Bangladesh',
                defaults={'is_verified': False},
            )


def remove_model_foods(apps, schema_editor):
    Food = apps.get_model('core', 'Food')
    Food.objects.filter(created_by=None, source=SOURCE).delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0009_user_username')]
    operations = [
        migrations.AlterField(
            model_name='food', name='kcal_100g',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True,
                                      validators=[MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='food', name='protein_100g',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True,
                                      validators=[MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='food', name='carbs_100g',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True,
                                      validators=[MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='food', name='fat_100g',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True,
                                      validators=[MinValueValidator(0)]),
        ),
        migrations.RunPython(seed_model_foods, remove_model_foods),
    ]
