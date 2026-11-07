from django.db import migrations


def copy_existing_food_values(apps, schema_editor):
    Food = apps.get_model('core', 'Food')
    NutritionSource = apps.get_model('core', 'NutritionSource')
    NutritionRecord = apps.get_model('core', 'NutritionRecord')
    source_ids = {}
    for food in Food.objects.all().iterator():
        key = (food.source or 'Unspecified', food.source_ref or '')
        if key not in source_ids:
            source_ids[key] = NutritionSource.objects.create(name=key[0], reference=key[1]).pk
        NutritionRecord.objects.create(
            food_id=food.pk, source_id=source_ids[key], version=1,
            verification_status='user_supplied' if food.created_by_id else 'unverified',
            nutrient_values={
                'kcal': str(food.kcal_100g),
                'protein_g': str(food.protein_100g),
                'carbs_g': str(food.carbs_100g),
                'fat_g': str(food.fat_100g),
            },
            calculation_method='Migrated from legacy per-100-g food fields',
        )


class Migration(migrations.Migration):
    dependencies = [('core', '0005_nutritiongoal_nutrienttarget_goalprogress_and_more')]
    operations = [migrations.RunPython(copy_existing_food_values, migrations.RunPython.noop)]
