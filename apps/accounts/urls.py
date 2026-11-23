from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("code/", views.request_code, name="request_code"),
    path("verify/", views.verify_code, name="verify_code"),
    path("change-mobile/", views.change_mobile, name="change_mobile"),
    path("logout/", views.logout, name="logout"),
]
