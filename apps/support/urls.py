from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("account/tickets/", views.ticket_list, name="tickets"),
    path("account/tickets/new/", views.ticket_new, name="ticket_new"),
    path("account/tickets/<int:pk>/", views.ticket_detail, name="ticket"),
    path("orders/item/<int:item_id>/report/", views.report_problem, name="report_problem"),
]
