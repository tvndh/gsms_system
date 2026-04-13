from django.contrib import admin
from django.urls import path, include
from django.conf import settings        
from django.conf.urls.static import static

urlpatterns = [
    # Đổi chữ 'admin/' thành 'django-admin/' để né đường của sếp
    path('django-admin/', admin.site.urls),
    
    # Toàn bộ đường link của sếp (bao gồm cả /admin/dashboard/) sẽ đi qua cái cửa này
    path('', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)