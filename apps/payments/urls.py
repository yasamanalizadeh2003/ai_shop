from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("callback/<str:gateway>/", views.callback, name="callback"),
    path("mock/<str:authority>/", views.mock_gateway, name="mock_gateway"),
]
