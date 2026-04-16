from django.urls import path
from . import views

urlpatterns = [
    # ==========================================
    # 1. TRANG PUBLIC (DÀNH CHO KHÁCH - PAGES)
    # ==========================================
    path('', views.guest_home, name='trang_chu'),
    path('gioi-thieu/', views.trang_gioi_thieu, name='gioi_thieu'),
    path('linh-vuc/<slug:slug>/', views.chi_tiet_linh_vuc, name='chi_tiet_linh_vuc'),
    path('tin-tuc/', views.trang_tin_tuc, name='tin_tuc'),
    path('tin-tuc/<int:id>/', views.chi_tiet_tin_tuc, name='chi_tiet_tin_tuc'),
    path('gui-danh-gia-tram/', views.gui_danh_gia_tram, name='gui_danh_gia_tram'),
    
    # Sản phẩm & Đánh giá
    path('san-pham/', views.trang_san_pham, name='san_pham'),
    path('san-pham/danh-gia/<int:sp_id>/', views.gui_danh_gia, name='gui_danh_gia'),
    
    path('lien-he/', views.trang_lien_he, name='lien_he'),
    
    # Đối tác & Tuyển dụng (Gửi Form)
    path('doi-tac/', views.trang_doi_tac, name='doi_tac'),
    path('gui-yeu-cau-b2b/', views.gui_yeu_cau_b2b, name='gui_yeu_cau_b2b'),
    
    path('tuyen-dung/', views.trang_tuyen_dung, name='tuyen_dung'),
    path('nop-ho-so/', views.nop_ho_so, name='nop_ho_so'),

    # ==========================================
    # 2. HỆ THỐNG XÁC THỰC (AUTH)
    # ==========================================
    path('login/', views.dang_nhap, name='login'),
    path('logout/', views.dang_xuat, name='logout'),

    # ==========================================
    # 3. KHU VỰC NHÂN VIÊN VẬN HÀNH (STAFF)
    # ==========================================
    path('pos-xang/', views.pos_xang, name='pos_xang'),
    path('pos-xang/process/', views.xu_ly_ban_hang, name='xu_ly_ban_hang'),
    path('nhan-vien/chot-ca/', views.staff_chot_ca, name='staff_chot_ca'),
    path('nhan-vien/bao-cao-tram/', views.bao_cao_tram, name='bao_cao_tram'),
    path('nhan-vien/xin-cap-xang/', views.tao_yeu_cau_nhap_hang, name='tao_yeu_cau_nhap_hang'),

    # ==========================================
    # 4. KHU VỰC QUẢN TRỊ VIÊN (ADMIN - TỔNG QUAN)
    # ==========================================
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/inbox/', views.admin_inbox, name='admin_inbox'), # Inbox quản lý Form
    path('admin/dieu-phoi-hang/', views.admin_import, name='admin_import'),
    path('admin/duyet-yeu-cau/<int:yc_id>/', views.duyet_yeu_cau, name='duyet_yeu_cau'),
    path('admin/quan-ly-gia/', views.quan_ly_gia, name='quan_ly_gia'),
    path('admin/export-excel/', views.xuat_excel_doanh_thu, name='xuat_excel_doanh_thu'),

    # ==========================================
    # 5. KHU VỰC QUẢN TRỊ VIÊN (ADMIN - CRUD)
    # ==========================================
    # Quản lý Trạm & Bồn
    path('admin/tram/', views.admin_danh_sach_tram, name='admin_trams'),
    path('admin/tram/them/', views.admin_them_tram, name='admin_them_tram'),
    path('admin/tram/sua/<int:id>/', views.admin_sua_tram, name='admin_sua_tram'),
    path('admin/tram/xoa/<int:id>/', views.admin_xoa_tram, name='admin_xoa_tram'),
    path('admin/bon-chua/', views.admin_bons, name='admin_bons'),
    path('admin/bon-chua/luu/', views.admin_luu_bon, name='admin_luu_bon'),
    path('admin/bon-chua/xoa/<int:bon_id>/', views.admin_xoa_bon, name='admin_xoa_bon'),

    # Quản lý Kho & Nhân sự
    path('admin/kho/', views.admin_danh_sach_kho, name='admin_khos'),
    path('admin/kho/them/', views.admin_them_kho, name='admin_them_kho'),
    path('admin/kho/sua/<int:id>/', views.admin_sua_kho, name='admin_sua_kho'),
    path('admin/kho/xoa/<int:id>/', views.admin_xoa_kho, name='admin_xoa_kho'),
    path('admin/nhan-su/', views.admin_danh_sach_nhan_su, name='admin_nhan_sus'),
    path('admin/nhan-su/them/', views.admin_them_nhan_su, name='admin_them_nhan_su'),
    path('admin/nhan-su/sua/<int:id>/', views.admin_sua_nhan_su, name='admin_sua_nhan_su'),
    path('admin/nhan-su/xoa/<int:id>/', views.admin_xoa_nhan_su, name='admin_xoa_nhan_su'),

    # Quản lý CMS (Sản phẩm trưng bày & Tin tức)
    path('admin/san-pham/', views.admin_san_pham, name='admin_san_pham'),
    path('admin/san-pham/luu/', views.admin_luu_san_pham, name='admin_luu_san_pham'),
    path('admin/san-pham/xoa/<int:sp_id>/', views.admin_xoa_san_pham, name='admin_xoa_san_pham'),
    
    path('admin/danh-muc/luu/', views.admin_luu_danh_muc, name='admin_luu_danh_muc'),
    path('admin/danh-muc/xoa/<int:dm_id>/', views.admin_xoa_danh_muc, name='admin_xoa_danh_muc'),
    
    path('admin/tin-tuc/', views.admin_tin_tuc, name='admin_tin_tuc'),
    path('admin/tin-tuc/them/', views.admin_tin_tuc_form, name='admin_them_tin_tuc'),
    path('admin/tin-tuc/sua/<int:tin_id>/', views.admin_tin_tuc_form, name='admin_sua_tin_tuc'),
    path('admin/tin-tuc/xoa/<int:tin_id>/', views.admin_xoa_tin_tuc, name='admin_xoa_tin_tuc'),
]