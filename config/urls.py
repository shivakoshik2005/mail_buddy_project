from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from mailer import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard, name='dashboard'),
    path('login/', views.smtp_login, name='smtp_login'),
    path('logout/', views.smtp_logout, name='smtp_logout'),
    path('compose/', views.compose, name='compose'),
    path('preview/<int:draft_id>/', views.preview, name='preview'),
    path('delete/<int:draft_id>/', views.delete_draft, name='delete_draft'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)