from django.urls import path
from. import views

urlpatterns = [
    path('', views.home_view, name="home"),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('protected/', views.ProtectedView.as_view(), name='protected'),
    path('create_circle/', views.create_circles_view, name='create_circle'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('circles/<int:circle_id>/', views.circle_detail_view, name='circle_detail'),
    path('join/<str:code>/', views.join_circle_view, name='join_circle'),
    path('find_circle/', views.find_circle_view, name='find_circle'),
]