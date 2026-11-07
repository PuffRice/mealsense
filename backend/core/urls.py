from django.urls import path
from . import views

urlpatterns = [
    path('auth/csrf/', views.csrf_token),
    path('auth/register/', views.RegisterView.as_view()),
    path('auth/login/', views.LoginView.as_view()),
    path('auth/logout/', views.LogoutView.as_view()),
    path('users/me/', views.MeView.as_view()),
    path('foods/', views.FoodListView.as_view()),
    path('meals/', views.MealListView.as_view()),
    path('meals/<uuid:pk>/', views.MealDetailView.as_view()),
    path('nutrition/daily/', views.DailyView.as_view()),
    path('nutrition/weekly/', views.WeeklyView.as_view()),
    path('nutrition/goals/', views.NutritionGoalsView.as_view()),
    path('recognitions/', views.RecognitionView.as_view()),
    path('recognitions/<uuid:pk>/', views.RecognitionDetailView.as_view()),
    path('images/<uuid:pk>/', views.PrivateImageView.as_view()),
]
