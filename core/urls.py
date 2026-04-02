from django.urls import path
from . import views

urlpatterns = [
    # 1. Trang chủ: Vào thẳng Bản đồ (Guest)
    path('', views.guest_home, name='trang_chu'),

    # 2. Hệ thống tài khoản
    path('login/', views.dang_nhap, name='login'),
    path('logout/', views.dang_xuat, name='logout'),
    
    # 3. Khu vực Admin
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('import/', views.admin_import, name='admin_import'),
    
    # --- SỬA LỖI TẠI ĐÂY: Đặt tên name='tao_du_lieu_mau' cho khớp với nút bấm HTML ---
    path('tao-data/', views.tao_du_lieu_mau, name='tao_du_lieu_mau'),

    # 4. Khu vực Nhân viên (POS)
    path('pos/', views.staff_pos, name='staff_pos'),
    path('pos/process/', views.xu_ly_ban_hang, name='xu_ly_ban_hang'),
    path('chot-ca/', views.staff_chot_ca, name='staff_chot_ca'),
    # Trang chủ
    path('gioi-thieu/', views.trang_gioi_thieu, name='gioi_thieu'),
    path('linh-vuc/<str:slug>/', views.trang_linh_vuc, name='linh_vuc'), # 1 trang dùng chung cho 5 lĩnh vực
    path('tin-tuc/', views.trang_tin_tuc, name='tin_tuc'),
    path('san-pham/', views.trang_san_pham, name='san_pham'),
    path('admin-portal/them-tram/', views.admin_add_station, name='admin_add_station'),
    path('pos/bao-cao-tram/', views.bao_cao_tram, name='bao_cao_tram'),
    path('tao-yeu-cau-nhap/', views.tao_yeu_cau_nhap, name='tao_yeu_cau_nhap'),
    path('duyet-yeu-cau/<int:req_id>/', views.duyet_yeu_cau, name='duyet_yeu_cau'),
    path('export-excel/', views.xuat_excel_doanh_thu, name='xuat_excel_doanh_thu'),
    path('lien-he/', views.trang_lien_he, name='lien_he'),
    path('quan-ly/nhan-su/', views.quan_ly_nhan_su, name='quan_ly_nhan_su'),
    path('quan-ly/nhan-su/thao-tac/', views.thao_tac_nhan_su, name='thao_tac_nhan_su'),
    path('quan-ly/gia-ban/', views.quan_ly_gia, name='quan_ly_gia'),
]