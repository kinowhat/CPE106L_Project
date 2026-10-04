from django.urls import path
from. import views

urlpatterns = [
    path('', views.home_view, name="home"),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('create_circle/', views.create_circles_view, name='create_circle'),
    path('calendar/', views.calendar_view, name='calendar'),
    path('circles/<int:circle_id>/', views.circle_detail_view, name='circle_detail'),
    path('join/<str:code>/', views.join_circle_view, name='join_circle'),
    path('find_circle/', views.find_circle_view, name='find_circle'),
    path('circles/<int:circle_id>/propose/', views.propose_event_view, name='propose_event'),
    path('proposals/<int:proposal_id>/vote/', views.vote_proposal_view, name='vote_proposal'),
    path('settings/timezone/', views.profile_settings_view, name='profile_settings'),
    path('circles/<int:circle_id>/timeblock/', views.time_block_detail_view, name='time_block_detail'),
    path('calendar/import/', views.import_calendar_view, name='import_calendar'),
    path('event/<int:event_id>/edit/', views.edit_event_view, name='edit_event'),
    path('event/<int:event_id>/delete/', views.delete_event_view, name='delete_event'),
    path('circles/<int:circle_id>/edit/', views.edit_circle_view, name='edit_circle'),
    path('circles/<int:circle_id>/delete/', views.delete_circle_view, name='delete_circle'),
    path('circles/<int:circle_id>/leave/', views.leave_circle_view, name='leave_circle'),
    path('calendar/export/', views.export_calendar_view, name='export_calendar'),
    path('circles/<int:circle_id>/quick_approve/', views.quick_approve_view, name='quick_approve'),
    path('circles/<int:circle_id>/export/', views.export_circle_calendar_view, name='export_circle_calendar'),
]