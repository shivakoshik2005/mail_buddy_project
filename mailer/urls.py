from django.urls import path
from . import views

urlpatterns = [
    # The empty string '' means this is the root of the mailer app
    path('', views.dashboard, name='dashboard'),
    
    # Maps to /compose/
    path('compose/', views.compose, name='compose'),
    
    # Maps to /preview/1/, /preview/2/, etc. The <int:draft_id> captures the ID.
    path('preview/<int:draft_id>/', views.preview, name='preview'),
]