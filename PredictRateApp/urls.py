from django.contrib import admin
from django.urls import path, include
from PredictRateApp import predict_logic
from .predict_logic import CurrencyPrediction, DeleteCache
urlpatterns = [
    path('forecast/',CurrencyPrediction.as_view(),name="forecast"),
    path('delete_cache/',DeleteCache.as_view(),name="delete_cache"),
    path('show_result/',CurrencyPrediction.as_view(),name="show_result")
]
