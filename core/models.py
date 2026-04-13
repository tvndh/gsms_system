from django.db import models
from django.contrib.auth.models import AbstractUser

# ==========================================
# 1. NGƯỜI DÙNG (Phân quyền 5 cấp bậc & Cách ly Trạm)
# ==========================================
class User(AbstractUser):
    # Định nghĩa 5 cấp bậc rõ ràng theo cơ cấu mới
    ROLES = (
        ('admin', 'Giám đốc / Quản trị viên'),
        ('ke_toan', 'Kế toán nội bộ'),
        ('truong_tram', 'Cửa hàng trưởng / Trưởng trạm'),
        ('nv_ban_hang', 'Nhân viên bán hàng (Siêu thị)'),
        ('nv_ban_xang', 'Nhân viên bơm xăng'),
    )
    role = models.CharField(max_length=20, choices=ROLES, default='nv_ban_xang', verbose_name="Chức vụ")
    full_name = models.CharField(max_length=100, verbose_name="Họ và tên")
    phone = models.CharField(max_length=15, verbose_name="Số điện thoại")
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    
    # Thông tin riêng cho nhân viên
    cccd = models.CharField(max_length=20, blank=True, null=True, verbose_name="CCCD")
    ca_lam_viec = models.CharField(max_length=50, blank=True, null=True, verbose_name="Ca làm việc")

    # Khóa chặt nhân viên vào 1 Trạm Xăng duy nhất
    # Admin và Kế toán có thể để trống (null) vì họ quản lý tổng
    tram_xang = models.ForeignKey(
        'TramXang', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='nhan_vien_truc_thuoc',
        verbose_name="Trạm trực thuộc"
    )

    def __str__(self):
        # Hiển thị đẹp trong Admin: "Nguyen Van A - Cửa hàng trưởng (Trạm số 1)"
        if self.tram_xang:
            return f"{self.username} ({self.get_role_display()} - {self.tram_xang.ten_tram})"
        return f"{self.username} ({self.get_role_display()})"


# ==========================================
# 2. TRẠM XĂNG (GIS)
# ==========================================
class TramXang(models.Model):
    ten_tram = models.CharField(max_length=100)
    dia_chi = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()
    
    def __str__(self): 
        return self.ten_tram


# ==========================================
# 3. BỒN CHỨA (Kho)
# ==========================================
class BonChua(models.Model):
    LOAI_XANG = (
        ('A95', 'Xăng A95'), 
        ('E5', 'Xăng E5'), 
        ('E10', 'Xăng Sinh Học E10'), 
        ('DO', 'Dầu DO')
    )
    tram = models.ForeignKey(TramXang, on_delete=models.CASCADE)
    ten_bon = models.CharField(max_length=50) 
    loai_nhien_lieu = models.CharField(max_length=10, choices=LOAI_XANG)
    suc_chua_toi_da = models.FloatField()
    muc_hien_tai = models.FloatField()
    
    def __str__(self): 
        return f"{self.ten_bon} - {self.loai_nhien_lieu} ({self.tram.ten_tram})"

    # Thuộc tính hiển thị phần trăm xăng trong bồn
    @property
    def phan_tram(self):
        if self.suc_chua_toi_da == 0: return 0
        return round((self.muc_hien_tai / self.suc_chua_toi_da) * 100, 1)

    # 👇 ĐÃ THÊM: Tự động lấy giá bán hiện tại từ bảng BangGiaNhienLieu
    @property
    def gia_ban_hien_tai(self):
        try:
            # Tìm giá của loại xăng tương ứng
            gia_obj = BangGiaNhienLieu.objects.get(loai_nhien_lieu=self.loai_nhien_lieu)
            return gia_obj.gia_ban
        except BangGiaNhienLieu.DoesNotExist:
            return 0  # Nếu Giám đốc chưa cài giá thì mặc định là 0đ


# ==========================================
# 4. HÓA ĐƠN & CHI TIẾT (Bán hàng)
# ==========================================
class HoaDon(models.Model):
    ma_hd = models.CharField(max_length=50, unique=True)
    nhan_vien = models.ForeignKey(User, on_delete=models.CASCADE)
    thoi_gian = models.DateTimeField(auto_now_add=True)
    tong_tien = models.FloatField()
    
    def __str__(self): 
        return self.ma_hd

class ChiTietHoaDon(models.Model):
    hoa_don = models.ForeignKey(HoaDon, on_delete=models.CASCADE)
    ten_mat_hang = models.CharField(max_length=100)
    so_luong = models.FloatField()
    don_gia = models.FloatField()
    thanh_tien = models.FloatField()


# ==========================================
# 5. NHÀ CUNG CẤP & PHIẾU NHẬP (GIS & Kho)
# ==========================================
class NhaCungCap(models.Model):
    ten_ncc = models.CharField(max_length=100)
    dia_chi = models.CharField(max_length=255)
    sdt = models.CharField(max_length=15)
    latitude = models.FloatField()
    longitude = models.FloatField()
    ton_kho_A95 = models.FloatField(default=500000)
    ton_kho_E5 = models.FloatField(default=500000)
    ton_kho_DO = models.FloatField(default=500000)
    ton_kho_E10 = models.FloatField(default=500000)

    def __str__(self): 
        return self.ten_ncc

class PhieuNhap(models.Model):
    ma_pn = models.CharField(max_length=20, unique=True)
    thoi_gian = models.DateTimeField(auto_now_add=True)
    nha_cung_cap = models.ForeignKey(NhaCungCap, on_delete=models.CASCADE)
    bon_chua = models.ForeignKey(BonChua, on_delete=models.CASCADE)
    so_lit_nhap = models.FloatField()
    thanh_tien = models.FloatField()
    gia_nhap_1_lit = models.FloatField(default=0, help_text="Giá mua sỉ từ Kho")
    cuoc_van_chuyen = models.FloatField(default=0, help_text="Cước xe bồn (dựa trên số Km)")
    tong_chi_phi = models.FloatField(default=0, help_text="Tiền hàng + Cước vận chuyển")

    def __str__(self): 
        return self.ma_pn


# ==========================================
# 6. TIN TỨC (Trang chủ doanh nghiệp)
# ==========================================
class TinTuc(models.Model):
    tieu_de = models.CharField(max_length=200)
    anh_bia = models.ImageField(upload_to='tin_tuc/anh_bia/', null=True, blank=True) 
    tom_tat = models.TextField()
    noi_dung = models.TextField()
    ngay_dang = models.DateTimeField(auto_now_add=True)

    def __str__(self): 
        return self.tieu_de
    class Meta:
        verbose_name = "Tin Tức"
        verbose_name_plural = "Quản lý Tin Tức"


# ==========================================
# 7. SẢN PHẨM & DANH MỤC (Trang chủ doanh nghiệp)
# ==========================================
class DanhMuc(models.Model):
    ten_dm = models.CharField(max_length=100)
    def __str__(self): 
        return self.ten_dm

class SanPham(models.Model):
    danh_muc = models.ForeignKey(DanhMuc, on_delete=models.CASCADE)
    ten_sp = models.CharField(max_length=100)
    gia_tham_khao = models.FloatField()
    anh_sp = models.ImageField(upload_to='san_pham/', null=True, blank=True)
    mo_ta = models.TextField()

    def __str__(self): 
        return self.ten_sp
    
    
# ==========================================
# 8. YÊU CẦU NHẬP HÀNG (Trạm trưởng gửi Admin)
# ==========================================
class YeuCauNhapHang(models.Model):
    TRANG_THAI = (
        ('cho_duyet', 'Đang chờ duyệt'),
        ('da_duyet', 'Đã duyệt & Đang giao'),
        ('tu_choi', 'Từ chối'),
    )
    tram = models.ForeignKey(TramXang, on_delete=models.CASCADE)
    nguoi_yeu_cau = models.ForeignKey(User, on_delete=models.CASCADE)
    loai_nhien_lieu = models.CharField(max_length=10, choices=BonChua.LOAI_XANG)
    so_luong = models.FloatField()
    thoi_gian = models.DateTimeField(auto_now_add=True)
    trang_thai = models.CharField(max_length=20, choices=TRANG_THAI, default='cho_duyet')
    ghi_chu = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.tram.ten_tram} - Yêu cầu {self.so_luong}L {self.loai_nhien_lieu}"


# ==========================================
# 9. BẢNG GIÁ NHIÊN LIỆU (Giám đốc cập nhật)
# ==========================================
class BangGiaNhienLieu(models.Model):
    loai_nhien_lieu = models.CharField(max_length=10, choices=BonChua.LOAI_XANG, unique=True, verbose_name="Loại Xăng Dầu")
    gia_ban = models.FloatField(verbose_name="Giá bán hiện tại (VNĐ/Lít)")
    ngay_cap_nhat = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.loai_nhien_lieu} - {self.gia_ban:,.0f} đ"


# ==========================================
# 10. CẤU HÌNH GIAO DIỆN (Giám đốc tự đổi Banner)
# ==========================================
class BannerTrangChu(models.Model):
    ten_chien_dich = models.CharField(max_length=100, verbose_name="Tên chiến dịch")
    
    # Ảnh Banner (Nên up ảnh ngang, kích thước lớn VD: 1920x600)
    anh_banner = models.ImageField(upload_to='banners/', verbose_name="Ảnh Banner")
    
    # Các dòng chữ hiển thị trên Banner
    tieu_de_chinh = models.CharField(max_length=200, blank=True, verbose_name="Tiêu đề chính (Chữ lớn)")
    tieu_de_phu = models.CharField(max_length=200, blank=True, verbose_name="Tiêu đề phụ (Chữ nhỏ)")
    
    # Trạng thái để biết cái nào được hiện ra Web
    dang_hien_thi = models.BooleanField(default=False, verbose_name="Đang hiển thị trên trang chủ?")
    
    ngay_tao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.ten_chien_dich

    def save(self, *args, **kwargs):
        # NÂNG CAO: Đảm bảo chỉ có DUY NHẤT 1 banner được hiển thị
        if self.dang_hien_thi:
            # Nếu cái này được chọn hiển thị, thì tìm và tắt hết các cái khác
            BannerTrangChu.objects.filter(dang_hien_thi=True).update(dang_hien_thi=False)
        super().save(*args, **kwargs)


# ==========================================
# 11. HỢP TÁC DOANH NGHIỆP (B2B / Nhượng quyền)
# ==========================================
class DoiTacB2B(models.Model):
    TRANG_THAI_B2B = (
        ('moi', 'Mới tiếp nhận'),
        ('da_lien_he', 'Đã liên hệ tư vấn'),
        ('dang_dam_phan', 'Đang đàm phán'),
        ('thanh_cong', 'Ký hợp đồng thành công'),
        ('that_bai', 'Hủy / Từ chối'),
    )
    ten_cong_ty = models.CharField(max_length=200, verbose_name="Tên Công Ty / Cá Nhân")
    so_dien_thoai = models.CharField(max_length=15, verbose_name="Số điện thoại")
    email = models.EmailField(blank=True, null=True, verbose_name="Email liên hệ")
    nhu_cau = models.CharField(max_length=200, verbose_name="Nhu cầu hợp tác")
    ghi_chu_admin = models.TextField(blank=True, null=True, verbose_name="Ghi chú của Admin")
    ngay_gui = models.DateTimeField(auto_now_add=True)
    trang_thai = models.CharField(max_length=20, choices=TRANG_THAI_B2B, default='moi', verbose_name="Trạng thái xử lý")

    def __str__(self):
        return f"{self.ten_cong_ty} - {self.nhu_cau}"
    class Meta:
        verbose_name = "Yêu cầu Hợp tác"
        verbose_name_plural = "Quản lý Hợp tác B2B"


# ==========================================
# 12. HỒ SƠ TUYỂN DỤNG (Careers)
# ==========================================
class HoSoUngVien(models.Model):
    TRANG_THAI_HS = (
        ('moi', 'Hồ sơ mới'),
        ('dang_xem', 'Đang xem xét'),
        ('phong_van', 'Hẹn phỏng vấn'),
        ('nhan_viec', 'Đã nhận việc'),
        ('tu_choi', 'Không phù hợp'),
    )
    vi_tri_ung_tuyen = models.CharField(max_length=100, verbose_name="Vị trí ứng tuyển")
    ho_ten = models.CharField(max_length=100, verbose_name="Họ và tên")
    so_dien_thoai = models.CharField(max_length=15, verbose_name="Số điện thoại")
    email = models.EmailField(blank=True, null=True)
    file_cv = models.FileField(upload_to='cv_ung_vien/', verbose_name="File CV (PDF/Word)")
    ngay_nop = models.DateTimeField(auto_now_add=True)
    trang_thai = models.CharField(max_length=20, choices=TRANG_THAI_HS, default='moi', verbose_name="Trạng thái hồ sơ")

    def __str__(self):
        return f"{self.ho_ten} - Ứng tuyển: {self.vi_tri_ung_tuyen}"
    class Meta:
        verbose_name = "Hồ sơ Ứng viên"
        verbose_name_plural = "Quản lý Tuyển dụng"


# ==========================================
# 13. LIÊN HỆ & GÓP Ý (Từ khách hàng)
# ==========================================
class LienHeGopY(models.Model):
    ho_ten = models.CharField(max_length=100, verbose_name="Họ và tên khách hàng")
    so_dien_thoai = models.CharField(max_length=15, verbose_name="Số điện thoại")
    tieu_de = models.CharField(max_length=200, verbose_name="Tiêu đề")
    noi_dung = models.TextField(verbose_name="Nội dung góp ý / thắc mắc")
    ngay_gui = models.DateTimeField(auto_now_add=True)
    da_xu_ly = models.BooleanField(default=False, verbose_name="Đã xử lý / Gọi lại?")

    def __str__(self):
        return f"[{'Đã xử lý' if self.da_xu_ly else 'MỚI'}] {self.ho_ten} - {self.tieu_de}"
    class Meta:
        verbose_name = "Liên hệ / Góp ý"
        verbose_name_plural = "Quản lý Góp ý Khách hàng"


# ==========================================
# 14. CỬA HÀNG TIỆN LỢI (GSMS Mart)
# ==========================================
class DanhMucMart(models.Model):
    ten_danh_muc = models.CharField(max_length=100, verbose_name="Tên Danh Mục (VD: Nước uống, Đồ ăn nhanh)")
    
    def __str__(self): 
        return self.ten_danh_muc
    class Meta:
        verbose_name = "Danh mục Mart"
        verbose_name_plural = "Danh mục Mart"

class SanPhamMart(models.Model):
    danh_muc = models.ForeignKey(DanhMucMart, on_delete=models.SET_NULL, null=True, verbose_name="Thuộc danh mục")
    ten_san_pham = models.CharField(max_length=100, verbose_name="Tên sản phẩm")
    gia_ban = models.FloatField(verbose_name="Giá bán (VNĐ)")
    ton_kho = models.IntegerField(default=0, verbose_name="Số lượng tồn kho")
    anh_san_pham = models.ImageField(upload_to='mart/', null=True, blank=True, verbose_name="Ảnh minh họa")

    def __str__(self): 
        return f"{self.ten_san_pham} - {self.gia_ban:,.0f}đ (Tồn: {self.ton_kho})"
    class Meta:
        verbose_name = "Sản phẩm Mart"
        verbose_name_plural = "Sản phẩm Mart"


# ==========================================
# 15. ĐÁNH GIÁ SẢN PHẨM (Từ Khách Hàng)
# ==========================================
class DanhGiaSanPham(models.Model):
    san_pham = models.ForeignKey(SanPham, on_delete=models.CASCADE, related_name='cac_danh_gia')
    ten_khach_hang = models.CharField(max_length=100, verbose_name="Tên khách hàng")
    so_sao = models.IntegerField(default=5, verbose_name="Số sao (1-5)")
    noi_dung = models.TextField(verbose_name="Nội dung đánh giá")
    ngay_gui = models.DateTimeField(auto_now_add=True)
    da_duyet = models.BooleanField(default=False, verbose_name="Đã duyệt (Cho phép hiện lên Web)")

    def __str__(self):
        return f"{self.ten_khach_hang} - {self.san_pham.ten_sp} ({self.so_sao} Sao)"
    class Meta:
        verbose_name = "Đánh giá Sản phẩm"
        verbose_name_plural = "Quản lý Đánh giá"