from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver

# ==========================================
# 1. NGƯỜI DÙNG (Phân quyền 4 cấp bậc & Cách ly Trạm)
# ==========================================
class User(AbstractUser):
    ROLES = (
        ('admin', 'Giám đốc / Quản trị viên'),
        ('ke_toan', 'Kế toán nội bộ'),
        ('truong_tram', 'Cửa hàng trưởng / Trưởng trạm'),
        ('nv_ban_xang', 'Nhân viên bơm xăng'),
    )
    role = models.CharField(max_length=20, choices=ROLES, default='nv_ban_xang', verbose_name="Chức vụ")
    full_name = models.CharField(max_length=100, verbose_name="Họ và tên")
    phone = models.CharField(max_length=15, verbose_name="Số điện thoại")
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    
    cccd = models.CharField(max_length=20, blank=True, null=True, verbose_name="CCCD")
    ca_lam_viec = models.CharField(max_length=50, blank=True, null=True, verbose_name="Ca làm việc")

    tram_xang = models.ForeignKey(
        'TramXang', on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='nhan_vien_truc_thuoc', verbose_name="Trạm trực thuộc"
    )

    def __str__(self):
        if self.tram_xang:
            return f"{self.username} ({self.get_role_display()} - {self.tram_xang.ten_tram})"
        return f"{self.username} ({self.get_role_display()})"


# ==========================================
# 2. TRẠM XĂNG (GIS)
# ==========================================
class TramXang(models.Model):
    TRANG_THAI = (
        ('hoat_dong', 'Đang hoạt động'),
        ('bao_tri', 'Đang bảo trì / Đóng cửa'),
    )
    ten_tram = models.CharField(max_length=100, verbose_name="Tên Trạm")
    dia_chi = models.CharField(max_length=255, verbose_name="Địa chỉ")
    latitude = models.FloatField(verbose_name="Vĩ độ (Latitude)")
    longitude = models.FloatField(verbose_name="Kinh độ (Longitude)")
    
    trang_thai = models.CharField(max_length=20, choices=TRANG_THAI, default='hoat_dong', verbose_name="Trạng thái")
    
    def __str__(self): 
        return f"{self.ten_tram} [{self.get_trang_thai_display()}]"
        
    class Meta:
        verbose_name = "Trạm Xăng"
        verbose_name_plural = "1. Quản lý Trạm Xăng"


# ==========================================
# 3. BỒN CHỨA (Kho tại trạm)
# ==========================================
class BonChua(models.Model):
    LOAI_XANG = (
        ('A95', 'Xăng A95'), ('E5', 'Xăng E5'), 
        ('E10', 'Xăng Sinh Học E10'), ('DO', 'Dầu DO')
    )
    tram = models.ForeignKey(TramXang, on_delete=models.CASCADE, verbose_name="Thuộc Trạm")
    ten_bon = models.CharField(max_length=50, verbose_name="Tên Bồn") 
    
    # KẾT NỐI VỚI SẢN PHẨM TRƯNG BÀY TỪ TỔNG KHO (B2B)
    loai_san_pham = models.ForeignKey(
        'SanPham', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Thuộc sản phẩm Catalog"
    )
    
    loai_nhien_lieu = models.CharField(max_length=10, choices=LOAI_XANG, verbose_name="Mã định danh (A95/E5/DO)")
    suc_chua_toi_da = models.FloatField(verbose_name="Sức chứa tối đa (Lít)")
    muc_hien_tai = models.FloatField(verbose_name="Mức hiện tại (Lít)")
    
    def __str__(self): 
        return f"{self.ten_bon} - {self.get_loai_nhien_lieu_display()} ({self.tram.ten_tram})"

    @property
    def phan_tram(self):
        if self.suc_chua_toi_da == 0: return 0
        return round((self.muc_hien_tai / self.suc_chua_toi_da) * 100, 1)

    @property
    def gia_ban_hien_tai(self):
        try:
            gia_obj = BangGiaNhienLieu.objects.get(loai_nhien_lieu=self.loai_nhien_lieu)
            return gia_obj.gia_ban
        except BangGiaNhienLieu.DoesNotExist:
            return 0 
            
    class Meta:
        verbose_name = "Bồn Chứa"
        verbose_name_plural = "2. Quản lý Bồn Chứa"


# ==========================================
# 4. HÓA ĐƠN & CHI TIẾT (Bán hàng)
# ==========================================
class HoaDon(models.Model):
    PT_THANH_TOAN = (
        ('tien_mat', 'Tiền mặt'),
        ('chuyen_khoan', 'Chuyển khoản / Momo'),
        ('the', 'Quẹt thẻ POS'),
    )
    ma_hd = models.CharField(max_length=50, unique=True, verbose_name="Mã HĐ")
    nhan_vien = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Nhân viên thu ngân")
    thoi_gian = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian")
    tong_tien = models.FloatField(verbose_name="Tổng tiền")
    
    phuong_thuc_thanh_toan = models.CharField(max_length=20, choices=PT_THANH_TOAN, default='tien_mat', verbose_name="Thanh toán bằng")
    
    def __str__(self): 
        return f"{self.ma_hd} ({self.get_phuong_thuc_thanh_toan_display()})"
        
    class Meta:
        verbose_name = "Hóa Đơn"
        verbose_name_plural = "3. Lịch sử Hóa Đơn"

class ChiTietHoaDon(models.Model):
    hoa_don = models.ForeignKey(HoaDon, on_delete=models.CASCADE, verbose_name="Thuộc Hóa Đơn")
    ten_mat_hang = models.CharField(max_length=100, verbose_name="Tên hàng / Dịch vụ")
    so_luong = models.FloatField(verbose_name="Số lượng")
    don_gia = models.FloatField(verbose_name="Đơn giá")
    thanh_tien = models.FloatField(verbose_name="Thành tiền")
    
    def __str__(self):
        return f"{self.ten_mat_hang} (x{self.so_luong})"
        
    class Meta:
        verbose_name = "Chi tiết HĐ"
        verbose_name_plural = "Chi tiết Hóa Đơn"


# ==========================================
# 5. NHÀ CUNG CẤP & PHIẾU NHẬP (Kho Tổng)
# ==========================================
class NhaCungCap(models.Model):
    ten_ncc = models.CharField(max_length=100, verbose_name="Tên Kho / NCC")
    dia_chi = models.CharField(max_length=255, verbose_name="Địa chỉ")
    sdt = models.CharField(max_length=15, verbose_name="Số điện thoại")
    latitude = models.FloatField(verbose_name="Vĩ độ")
    longitude = models.FloatField(verbose_name="Kinh độ")
    ton_kho_A95 = models.FloatField(default=500000, verbose_name="Tồn kho A95")
    ton_kho_E5 = models.FloatField(default=500000, verbose_name="Tồn kho E5")
    ton_kho_DO = models.FloatField(default=500000, verbose_name="Tồn kho DO")
    ton_kho_E10 = models.FloatField(default=500000, verbose_name="Tồn kho E10")

    def __str__(self): 
        return self.ten_ncc
        
    class Meta:
        verbose_name = "Kho Tổng / NCC"
        verbose_name_plural = "4. Quản lý Kho Tổng"

class PhieuNhap(models.Model):
    ma_pn = models.CharField(max_length=20, unique=True, verbose_name="Mã Phiếu Nhập")
    thoi_gian = models.DateTimeField(auto_now_add=True, verbose_name="Ngày xuất")
    nha_cung_cap = models.ForeignKey(NhaCungCap, on_delete=models.CASCADE, verbose_name="Từ Kho Tổng")
    bon_chua = models.ForeignKey(BonChua, on_delete=models.CASCADE, verbose_name="Nhập vào Bồn")
    so_lit_nhap = models.FloatField(verbose_name="Số lít")
    gia_nhap_1_lit = models.FloatField(default=0, help_text="Giá mua sỉ từ Kho")
    cuoc_van_chuyen = models.FloatField(default=0, help_text="Cước xe bồn (dựa trên số Km)")
    thanh_tien = models.FloatField(verbose_name="Tiền hàng")
    tong_chi_phi = models.FloatField(default=0, help_text="Tiền hàng + Cước vận chuyển")

    def __str__(self): 
        return self.ma_pn
        
    class Meta:
        verbose_name = "Phiếu Điều Phối"
        verbose_name_plural = "5. Phiếu Điều Phối (Lịch sử)"


# ==========================================
# 6. SẢN PHẨM TRƯNG BÀY (Catalog / Dịch vụ)
# ==========================================
class DanhMuc(models.Model):
    ten_dm = models.CharField(max_length=100, verbose_name="Tên Danh mục")
    
    def __str__(self): return self.ten_dm
    class Meta:
        verbose_name = "Danh mục Sản phẩm"
        verbose_name_plural = "6. Danh mục Catalog"

class SanPham(models.Model):
    danh_muc = models.ForeignKey(DanhMuc, on_delete=models.CASCADE, verbose_name="Thuộc danh mục")
    ten_sp = models.CharField(max_length=100, verbose_name="Tên Sản phẩm / Dịch vụ")
    gia_tham_khao = models.FloatField(verbose_name="Giá tham khảo")
    anh_sp = models.ImageField(upload_to='san_pham/', null=True, blank=True, verbose_name="Ảnh minh họa")
    mo_ta = models.TextField(blank=True, null=True, verbose_name="Mô tả chi tiết")

    def __str__(self): 
        return self.ten_sp
        
    class Meta:
        verbose_name = "Sản phẩm Trưng bày"
        verbose_name_plural = "7. Quản lý Sản phẩm (Catalog)"


# ==========================================
# 7. BẢNG GIÁ NHIÊN LIỆU (Hệ thống)
# ==========================================
class BangGiaNhienLieu(models.Model):
    loai_nhien_lieu = models.CharField(max_length=10, choices=BonChua.LOAI_XANG, unique=True, verbose_name="Loại Xăng Dầu")
    gia_ban = models.FloatField(verbose_name="Giá bán hiện tại (VNĐ/Lít)")
    ngay_cap_nhat = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.loai_nhien_lieu} - {self.gia_ban:,.0f} đ"
        
    class Meta:
        verbose_name = "Bảng Giá Nhiên Liệu"
        verbose_name_plural = "8. Bảng Giá Hệ Thống"


# ==========================================
# 8. YÊU CẦU NHẬP HÀNG (Trạm -> Tổng)
# ==========================================
class YeuCauNhapHang(models.Model):
    TRANG_THAI = (
        ('cho_duyet', 'Đang chờ duyệt'),
        ('da_duyet', 'Đã duyệt & Đang giao'),
        ('tu_choi', 'Từ chối'),
    )
    tram = models.ForeignKey(TramXang, on_delete=models.CASCADE, verbose_name="Trạm yêu cầu")
    nguoi_yeu_cau = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Người gửi")
    loai_nhien_lieu = models.CharField(max_length=10, choices=BonChua.LOAI_XANG, verbose_name="Loại nhiên liệu")
    so_luong = models.FloatField(verbose_name="Số lượng (Lít)")
    thoi_gian = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian gửi")
    trang_thai = models.CharField(max_length=20, choices=TRANG_THAI, default='cho_duyet', verbose_name="Trạng thái")
    ghi_chu = models.TextField(blank=True, null=True, verbose_name="Ghi chú")

    def __str__(self):
        return f"{self.tram.ten_tram} - Yêu cầu {self.so_luong}L {self.loai_nhien_lieu}"
    class Meta:
        verbose_name = "Yêu cầu Nhập hàng"
        verbose_name_plural = "9. Yêu cầu Nhập hàng"


# ==========================================
# 9. MARKETING & KHÁCH HÀNG (CMS)
# ==========================================
class TinTuc(models.Model):
    tieu_de = models.CharField(max_length=200, verbose_name="Tiêu đề bài viết")
    anh_bia = models.ImageField(upload_to='tin_tuc/anh_bia/', null=True, blank=True, verbose_name="Ảnh bìa") 
    tom_tat = models.TextField(verbose_name="Tóm tắt ngắn")
    noi_dung = models.TextField(verbose_name="Nội dung chi tiết")
    ngay_dang = models.DateTimeField(auto_now_add=True, verbose_name="Ngày đăng")

    def __str__(self): return self.tieu_de
    class Meta:
        verbose_name = "Tin Tức & Sự Kiện"
        verbose_name_plural = "10. Quản lý Tin Tức"

class DanhGiaTram(models.Model):
    tram = models.ForeignKey(TramXang, on_delete=models.CASCADE, related_name='cac_danh_gia') # Liên kết tới Trạm
    ten_khach_hang = models.CharField(max_length=100)
    so_sao = models.IntegerField(default=5)
    noi_dung = models.TextField()
    da_duyet = models.BooleanField(default=False)
    ngay_gui = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.ten_khach_hang} - {self.tram.ten_tram}"

class DoiTacB2B(models.Model):
    TRANG_THAI_B2B = (
        ('moi', 'Mới tiếp nhận'), ('da_lien_he', 'Đã liên hệ tư vấn'),
        ('dang_dam_phan', 'Đang đàm phán'), ('thanh_cong', 'Ký hợp đồng thành công'), ('that_bai', 'Hủy / Từ chối'),
    )
    ten_cong_ty = models.CharField(max_length=200, verbose_name="Tên Công Ty / Cá Nhân")
    so_dien_thoai = models.CharField(max_length=15, verbose_name="Số điện thoại")
    email = models.EmailField(blank=True, null=True, verbose_name="Email liên hệ")
    nhu_cau = models.CharField(max_length=200, verbose_name="Nhu cầu hợp tác")
    ghi_chu_admin = models.TextField(blank=True, null=True, verbose_name="Ghi chú của Admin")
    ngay_gui = models.DateTimeField(auto_now_add=True)
    trang_thai = models.CharField(max_length=20, choices=TRANG_THAI_B2B, default='moi', verbose_name="Trạng thái xử lý")

    def __str__(self): return f"{self.ten_cong_ty} - {self.nhu_cau}"
    class Meta:
        verbose_name = "Yêu cầu Hợp tác"
        verbose_name_plural = "12. Quản lý Hợp tác B2B"

class HoSoUngVien(models.Model):
    TRANG_THAI_HS = (
        ('moi', 'Hồ sơ mới'), ('dang_xem', 'Đang xem xét'),
        ('phong_van', 'Hẹn phỏng vấn'), ('nhan_viec', 'Đã nhận việc'), ('tu_choi', 'Không phù hợp'),
    )
    vi_tri_ung_tuyen = models.CharField(max_length=100, verbose_name="Vị trí ứng tuyển")
    ho_ten = models.CharField(max_length=100, verbose_name="Họ và tên")
    so_dien_thoai = models.CharField(max_length=15, verbose_name="Số điện thoại")
    email = models.EmailField(blank=True, null=True)
    file_cv = models.FileField(upload_to='cv_ung_vien/', verbose_name="File CV")
    ngay_nop = models.DateTimeField(auto_now_add=True)
    trang_thai = models.CharField(max_length=20, choices=TRANG_THAI_HS, default='moi', verbose_name="Trạng thái hồ sơ")

    def __str__(self): return f"{self.ho_ten} - {self.vi_tri_ung_tuyen}"
    class Meta:
        verbose_name = "Hồ sơ Ứng viên"
        verbose_name_plural = "13. Quản lý Tuyển dụng"

class LienHeGopY(models.Model):
    ho_ten = models.CharField(max_length=100, verbose_name="Họ và tên khách hàng")
    so_dien_thoai = models.CharField(max_length=15, verbose_name="Số điện thoại")
    email = models.EmailField(max_length=255, null=True, blank=True)
    tieu_de = models.CharField(max_length=200, verbose_name="Tiêu đề")
    noi_dung = models.TextField(verbose_name="Nội dung")
    ngay_gui = models.DateTimeField(auto_now_add=True)
    da_xu_ly = models.BooleanField(default=False, verbose_name="Đã xử lý / Gọi lại?")

    def __str__(self): return f"[{'Đã xử lý' if self.da_xu_ly else 'MỚI'}] {self.ho_ten}"
    class Meta:
        verbose_name = "Liên hệ / Góp ý"
        verbose_name_plural = "14. Quản lý Góp ý Khách hàng"


# ==========================================
# 10. AUTO-CREATE TANK SIGNAL (Đẻ bồn tự động)
# ==========================================
@receiver(post_save, sender=TramXang)
def tao_bon_mac_dinh_cho_tram_moi(sender, instance, created, **kwargs):
    if created:
        BonChua.objects.create(tram=instance, ten_bon="Bồn A95 Mặc định", loai_nhien_lieu="A95", suc_chua_toi_da=15000, muc_hien_tai=0)
        BonChua.objects.create(tram=instance, ten_bon="Bồn E5 Mặc định", loai_nhien_lieu="E5", suc_chua_toi_da=10000, muc_hien_tai=0)
        BonChua.objects.create(tram=instance, ten_bon="Bồn DO Mặc định", loai_nhien_lieu="DO", suc_chua_toi_da=20000, muc_hien_tai=0)
        print(f"✅ Đã tự động tạo 3 bồn chứa mặc định cho trạm: {instance.ten_tram}")