import json
from urllib import request
import uuid
import random
import string
import logging
from datetime import timedelta

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.db import transaction # Đã thêm transaction
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model

# GOM HẾT MODEL LÊN ĐÂY IMPORT 1 LẦN
from .models import (
    TramXang, BonChua, NhaCungCap, HoaDon, ChiTietHoaDon, 
    TinTuc, DanhMuc, SanPham, PhieuNhap, YeuCauNhapHang, BangGiaNhienLieu,BannerTrangChu
)

User = get_user_model()
logger = logging.getLogger(__name__)

# ==========================================
# 1. HỆ THỐNG XÁC THỰC (AUTH)
# ==========================================

def dang_nhap(request):
    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            messages.success(request, f"Xin chào {user.username}!")
            
            if user.role == 'admin' or user.is_superuser:
                return redirect('admin_dashboard')
            else:
                return redirect('staff_pos')
        else:
            messages.error(request, "Tên đăng nhập hoặc mật khẩu không đúng!")
    return render(request, 'login.html')

def dang_xuat(request):
    logout(request)
    messages.info(request, "Đăng xuất thành công.")
    return redirect('login')


# ==========================================
# 2. KHU VỰC QUẢN TRỊ (ADMIN)
# ==========================================

@login_required
def admin_dashboard(request):
    if request.user.role != 'admin' and not request.user.is_superuser:
        messages.warning(request, "Bạn không có quyền truy cập!")
        return redirect('trang_chu')

    today = timezone.now().date()
    ds_bon = BonChua.objects.all()

    stats = HoaDon.objects.filter(thoi_gian__date=today).aggregate(
        total_money=Sum('tong_tien'), total_tx=Count('id')
    )
    doanh_thu = stats['total_money'] or 0
    so_giao_dich = stats['total_tx'] or 0
    san_luong = ChiTietHoaDon.objects.filter(hoa_don__thoi_gian__date=today).aggregate(Sum('so_luong'))['so_luong__sum'] or 0

    # TÍNH LỢI NHUẬN ƯỚC TÍNH TOÀN HỆ THỐNG (Biên lợi nhuận ròng tạm tính 6.5%)
    loi_nhuan_hom_nay = doanh_thu * 0.065

    tu_khoa = request.GET.get('q', '')
    ds_tram = TramXang.objects.all()
    
    if tu_khoa:
        ds_tram = ds_tram.filter(ten_tram__icontains=tu_khoa)

    bang_doanh_thu = []
    for t in ds_tram:
        hds = HoaDon.objects.filter(nhan_vien__tram_xang=t, thoi_gian__date=today)
        dt = hds.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0
        sl = ChiTietHoaDon.objects.filter(hoa_don__in=hds).aggregate(Sum('so_luong'))['so_luong__sum'] or 0
        
        # TÍNH LỢI NHUẬN ƯỚC TÍNH TỪNG TRẠM
        ln_tram = dt * 0.065
        
        bang_doanh_thu.append({
            'tram': t,
            'doanh_thu': dt,
            'loi_nhuan': ln_tram, # <-- Đã thêm biến lợi nhuận vào danh sách
            'san_luong': sl,
            'so_don': hds.count()
        })
    bang_doanh_thu.sort(key=lambda x: x['doanh_thu'], reverse=True)

    now = timezone.now()
    
    # Biểu đồ
    day_data = {'labels': [], 'revenue': [], 'volume': []}
    for i in range(6, -1, -1):
        dt = now - timedelta(days=i)
        day_data['labels'].append(dt.strftime("%d/%m"))
        hds = HoaDon.objects.filter(thoi_gian__date=dt.date())
        day_data['revenue'].append(float(hds.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0) / 1000000)
        day_data['volume'].append(float(ChiTietHoaDon.objects.filter(hoa_don__in=hds).aggregate(Sum('so_luong'))['so_luong__sum'] or 0))

    month_data = {'labels': ['Tuần 1', 'Tuần 2', 'Tuần 3', 'Tuần 4'], 'revenue': [0,0,0,0], 'volume': [0,0,0,0]}
    for i in range(28):
        dt = now - timedelta(days=i)
        week_idx = 3 - (i // 7)
        hds = HoaDon.objects.filter(thoi_gian__date=dt.date())
        month_data['revenue'][week_idx] += float(hds.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0) / 1000000
        month_data['volume'][week_idx] += float(ChiTietHoaDon.objects.filter(hoa_don__in=hds).aggregate(Sum('so_luong'))['so_luong__sum'] or 0)

    year_data = {'labels': [f'T{i}' for i in range(1, 13)], 'revenue': [0]*12, 'volume': [0]*12}
    hds_year = HoaDon.objects.filter(thoi_gian__year=now.year)
    for hd in hds_year:
        m_idx = hd.thoi_gian.month - 1
        year_data['revenue'][m_idx] += float(hd.tong_tien or 0) / 1000000
        sl_sum = ChiTietHoaDon.objects.filter(hoa_don=hd).aggregate(Sum('so_luong'))['so_luong__sum'] or 0
        year_data['volume'][m_idx] += float(sl_sum)

    quarter_data = {
        'labels': ['Quý 1', 'Quý 2', 'Quý 3', 'Quý 4'],
        'revenue': [sum(year_data['revenue'][0:3]), sum(year_data['revenue'][3:6]), sum(year_data['revenue'][6:9]), sum(year_data['revenue'][9:12])],
        'volume': [sum(year_data['volume'][0:3]), sum(year_data['volume'][3:6]), sum(year_data['volume'][6:9]), sum(year_data['volume'][9:12])]
    }

    chart_data = {'day': day_data, 'month': month_data, 'quarter': quarter_data, 'year': year_data}
    
    context = {
        'ds_bon': ds_bon,
        'doanh_thu_hom_nay': doanh_thu,
        'loi_nhuan_hom_nay': loi_nhuan_hom_nay, # <-- Đã đẩy biến ra context cho HTML bắt
        'san_luong_hom_nay': san_luong,
        'so_giao_dich': so_giao_dich,
        'chart_data_json': json.dumps(chart_data),
        'bang_doanh_thu': bang_doanh_thu,
        'tu_khoa': tu_khoa,
    }
    return render(request, 'admin_dashboard.html', context)

@login_required
def admin_import(request):
    if request.user.role != 'admin' and not request.user.is_superuser:
        messages.error(request, "Bạn không có quyền truy cập trang nhập hàng!")
        return redirect('trang_chu')

    if request.method == 'POST':
        try:
            ncc_id = request.POST.get('ncc_id')
            bon_id = request.POST.get('bon_chua')
            so_lit = float(request.POST.get('so_lit', 0))
            
            if not bon_id or not ncc_id:
                messages.error(request, "Vui lòng chọn đầy đủ Kho cung cấp và Bồn chứa!")
                return redirect('admin_import')
                
            with transaction.atomic():
                bon = BonChua.objects.select_for_update().get(id=bon_id)
                ncc = NhaCungCap.objects.select_for_update().get(id=ncc_id) # Lấy data Kho Tổng
                loai_nl = bon.loai_nhien_lieu
                
                # 1. KIỂM TRA XEM KHO TỔNG CÒN ĐỦ HÀNG KHÔNG?
                # Dùng getattr để lấy linh hoạt cột ton_kho_A95, ton_kho_E5...
                ton_kho_hien_tai = getattr(ncc, f'ton_kho_{loai_nl}', 0) 
                
                if ton_kho_hien_tai < so_lit:
                    messages.error(request, f"LỖI: Kho {ncc.ten_ncc} chỉ còn {ton_kho_hien_tai:,.0f} Lít {loai_nl}. Không đủ xuất!")
                    return redirect('admin_import')

                # 2. KIỂM TRA BỒN TRẠM CÓ BỊ TRÀN KHÔNG?
                if bon.muc_hien_tai + so_lit > bon.suc_chua_toi_da:
                    messages.error(request, f"Cảnh báo: Bồn {bon.ten_bon} không đủ sức chứa!")
                else:
                    # 3. THỰC HIỆN ĐIỀU CHUYỂN: TRỪ KHO TỔNG, CỘNG BỒN TRẠM
                    setattr(ncc, f'ton_kho_{loai_nl}', ton_kho_hien_tai - so_lit)
                    ncc.save() # Lưu Kho Tổng

                    bon.muc_hien_tai += so_lit
                    bon.save() # Lưu Bồn Trạm
                    
                    # 4. TÍNH TOÁN KINH TẾ (Phần của bạn)
                    gia_nhap_si = 21000 
                    so_km = float(request.POST.get('khoang_cach', 0)) # Bắt số Km từ giao diện bản đồ
                    tien_cuoc = so_km * 15000
                    tien_hang = so_lit * gia_nhap_si

                    # 5. TẠO PHIẾU NHẬP
                    PhieuNhap.objects.create(
                        ma_pn=f"PN-{timezone.now().strftime('%d%m%H%M%S')}-{random.randint(10,99)}",
                        nha_cung_cap_id=ncc_id,
                        bon_chua=bon,
                        so_lit_nhap=so_lit,
                        gia_nhap_1_lit=gia_nhap_si,
                        cuoc_van_chuyen=tien_cuoc,
                        tong_chi_phi=tien_hang + tien_cuoc,
                        thanh_tien=tien_hang
                    )

                    # 6. DỌN DẸP YÊU CẦU CỦA TRƯỞNG TRẠM
                    YeuCauNhapHang.objects.filter(
                        tram=bon.tram,
                        loai_nhien_lieu=loai_nl,
                        trang_thai='cho_duyet'
                    ).update(trang_thai='da_duyet')

                    messages.success(request, f"Đã xuất {so_lit:,.0f} lít từ Kho {ncc.ten_ncc} đến {bon.tram.ten_tram}.")
                    return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Lỗi nhập liệu: {e}")

    # LẤY DỮ LIỆU ĐỂ VẼ BẢN ĐỒ
    ds_ncc = NhaCungCap.objects.all()
    ds_bon = BonChua.objects.select_related('tram').all()

    ncc_list = [{'id': n.id, 'name': n.ten_ncc, 'lat': float(n.latitude or 0), 'lng': float(n.longitude or 0), 'address': n.dia_chi} for n in ds_ncc]

    tank_list = []
    station_dict = {}

    for b in ds_bon:
        phan_tram = round((b.muc_hien_tai / b.suc_chua_toi_da) * 100, 1) if b.suc_chua_toi_da > 0 else 0
        tank_list.append({
            'id': b.id, 'ten_bon': b.ten_bon, 'loai': b.get_loai_nhien_lieu_display(),
            'muc_hien_tai': float(b.muc_hien_tai), 'suc_chua': float(b.suc_chua_toi_da),
            'phan_tram': phan_tram, 'tram_id': b.tram.id
        })
        if b.tram.id not in station_dict:
            station_dict[b.tram.id] = {'id': b.tram.id, 'name': b.tram.ten_tram, 'lat': float(b.tram.latitude or 0), 'lng': float(b.tram.longitude or 0)}

    # LẤY DANH SÁCH YÊU CẦU CẤP XĂNG TỪ TRẠM GỬI LÊN (Nằm đúng vị trí)
    ds_yeu_cau = YeuCauNhapHang.objects.filter(trang_thai='cho_duyet').order_by('-id')

    context = {
        'ds_ncc': ds_ncc, 
        'ncc_json': json.dumps(ncc_list), 
        'tank_json': json.dumps(tank_list),
        'station_json': json.dumps(list(station_dict.values())), 
        'ds_yeu_cau': ds_yeu_cau,
    }
    return render(request, 'admin_import.html', context)
@login_required
def admin_add_station(request):
    if request.user.role != 'admin' and not request.user.is_superuser:
        messages.error(request, "Bạn không có quyền thêm trạm xăng!")
        return redirect('staff_pos')

    if request.method == 'POST':
        ten_tram = request.POST.get('ten_tram')
        dia_chi = request.POST.get('dia_chi')
        lat = request.POST.get('latitude')
        lng = request.POST.get('longitude')

        if not lat or not lng:
            messages.error(request, "Lỗi: Bạn chưa click chọn vị trí trên Bản đồ!")
            return render(request, 'admin_add_station')

        try:
            with transaction.atomic(): # Dùng transaction an toàn
                lat = float(lat)
                lng = float(lng)

                tram_moi = TramXang.objects.create(
                    ten_tram=ten_tram,
                    dia_chi=dia_chi,
                    latitude=lat,
                    longitude=lng
                )

                nhien_lieu_duoc_chon = request.POST.getlist('nhien_lieu')
                thong_so_bon = {
                    'A95': {'ten': 'Bồn A95', 'max': 15000},
                    'E5':  {'ten': 'Bồn E5', 'max': 10000},
                    'E10': {'ten': 'Bồn E10', 'max': 10000},
                    'DO':  {'ten': 'Bồn DO', 'max': 20000},
                }

                for nl in nhien_lieu_duoc_chon:
                    if nl in thong_so_bon:
                        BonChua.objects.create(
                            tram=tram_moi,
                            ten_bon=thong_so_bon[nl]['ten'],
                            loai_nhien_lieu=nl,
                            suc_chua_toi_da=thong_so_bon[nl]['max'],
                            muc_hien_tai=0
                        )

                # TẠO TÀI KHOẢN VỚI PASS NGẪU NHIÊN
                random_pass_truong = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
                random_pass_nv = ''.join(random.choices(string.ascii_letters + string.digits, k=6))

                tk_truong = f"truongtram_{tram_moi.id}"
                User.objects.create_user(
                    username=tk_truong, password=random_pass_truong, full_name=f"Trưởng trạm {tram_moi.id}",
                    role="tram_truong", tram_xang=tram_moi
                )

                tk_nhanvien = f"nhanvien_{tram_moi.id}"
                User.objects.create_user(
                    username=tk_nhanvien, password=random_pass_nv, full_name=f"Nhân viên {tram_moi.id}",
                    role="staff", tram_xang=tram_moi
                )

                messages.success(request, f"Đã thêm trạm! TK Trưởng: {tk_truong}(Pass: {random_pass_truong}) | TK NV: {tk_nhanvien}(Pass: {random_pass_nv})")
                return redirect('admin_dashboard')

        except Exception as e:
            messages.error(request, f"Lỗi chi tiết: {str(e)}")
    # Thêm 2 dòng này trước khi return
        ds_tram = TramXang.objects.all().order_by('-id')
        return render(request, 'admin_add_station.html', {'ds_tram': ds_tram})
    return render(request, 'admin_add_station.html')
@login_required
def admin_add_ncc(request):
    # Chặn quyền y như các trang quản lý khác
    if request.user.role != 'admin' and not request.user.is_superuser:
        messages.error(request, "Bạn không có quyền thêm Nhà cung cấp!")
        return redirect('trang_chu')

    if request.method == 'POST':
        try:
            ten_ncc = request.POST.get('ten_ncc')
            sdt = request.POST.get('sdt')
            dia_chi = request.POST.get('dia_chi')
            lat = request.POST.get('latitude')
            lng = request.POST.get('longitude')

            if not lat or not lng:
                messages.error(request, "Lỗi: Bạn chưa click chọn vị trí Kho trên Bản đồ!")
                return render(request, 'admin_add_ncc')

            # Lưu vào Database
            from .models import NhaCungCap
            NhaCungCap.objects.create(
                ten_ncc=ten_ncc,
                sdt=sdt,
                dia_chi=dia_chi,
                latitude=float(lat),
                longitude=float(lng)
            )

            messages.success(request, f"Đã thêm Tổng kho / Nhà cung cấp: {ten_ncc} thành công!")
            # Thêm xong thì đá về trang Nhập hàng để thấy kết quả luôn
            return redirect('admin_import')

        except Exception as e:
            messages.error(request, f"Có lỗi xảy ra khi lưu: {e}")
    
        ds_ncc = NhaCungCap.objects.all().order_by('-id')
        return render(request, 'admin_add_ncc.html', {'ds_ncc': ds_ncc})
    return render(request, 'admin_add_ncc.html')
# Quản lý tin tức
from django.shortcuts import get_object_or_404

@login_required
def admin_tin_tuc(request):
    if request.user.role != 'admin' and not request.user.is_superuser:
        messages.error(request, "Bạn không có quyền truy cập!")
        return redirect('trang_chu')
    
    ds_tin = TinTuc.objects.all().order_by('-ngay_dang')
    return render(request, 'admin_tin_tuc.html', {'ds_tin': ds_tin})

@login_required
def admin_tin_tuc_form(request, tin_id=None):
    if request.user.role != 'admin' and not request.user.is_superuser:
        return redirect('trang_chu')

    # Nếu có tin_id truyền vào nghĩa là đang Sửa, nếu không là Thêm mới
    tin_hien_tai = get_object_or_404(TinTuc, id=tin_id) if tin_id else None

    if request.method == 'POST':
        try:
            tieu_de = request.POST.get('tieu_de')
            tom_tat = request.POST.get('tom_tat')
            noi_dung = request.POST.get('noi_dung')
            anh_bia = request.FILES.get('anh_bia') # 🚨 Lấy file ảnh từ request.FILES

            if not tin_hien_tai:
                tin_hien_tai = TinTuc() # Tạo mới

            tin_hien_tai.tieu_de = tieu_de
            tin_hien_tai.tom_tat = tom_tat
            tin_hien_tai.noi_dung = noi_dung
            
            if anh_bia: # Chỉ cập nhật ảnh nếu Admin có chọn file mới
                tin_hien_tai.anh_bia = anh_bia

            tin_hien_tai.save()
            messages.success(request, "Lưu bài viết thành công!")
            return redirect('admin_tin_tuc')
        except Exception as e:
            messages.error(request, f"Lỗi: {e}")

    return render(request, 'admin_tin_tuc_form.html', {'tin': tin_hien_tai})

@login_required
def admin_xoa_tin_tuc(request, tin_id):
    if request.user.role == 'admin' or request.user.is_superuser:
        tin = get_object_or_404(TinTuc, id=tin_id)
        tin.delete()
        messages.success(request, "Đã xóa bài viết!")
    return redirect('admin_tin_tuc')
# ==========================================
# 3. KHU VỰC NHÂN VIÊN (STAFF POS)
# ==========================================

@login_required
def staff_pos(request):
    user = request.user
    if user.role == 'admin'or user.is_superuser:
        return redirect('admin_dashboard')

    if not user.tram_xang:
        messages.error(request, "Tài khoản của bạn chưa được phân công về Trạm Xăng nào!")
        return redirect('login')

    tram_cua_toi = user.tram_xang
    today = timezone.now().date()

    ds_bon_raw = BonChua.objects.filter(tram=tram_cua_toi)
    ds_bon = []
    bon_can_canh_bao = []
    
    # Lấy toàn bộ bảng giá
    bang_gia_qs = BangGiaNhienLieu.objects.all()
    dict_gia = {item.loai_nhien_lieu: item.gia_ban for item in bang_gia_qs}

    for b in ds_bon_raw:
        ty_le_nhap = (b.muc_hien_tai / b.suc_chua_toi_da) * 100 if b.suc_chua_toi_da > 0 else 0
        b.gia_ban_hien_tai = dict_gia.get(b.loai_nhien_lieu, 20000)
        
        ds_bon.append(b)
        if ty_le_nhap < 20:
            bon_can_canh_bao.append(b)

    if user.role == 'tram_truong':
        # Bỏ thoi_gian__date=today, cứ lấy 20 đơn mới nhất của Trạm
        lich_su = HoaDon.objects.filter(nhan_vien__tram_xang=tram_cua_toi).order_by('-thoi_gian')[:20]
    else:
        # Bỏ thoi_gian__date=today, cứ lấy 10 đơn mới nhất của Nhân viên đó
        lich_su = HoaDon.objects.filter(nhan_vien=user).order_by('-thoi_gian')[:10]

    context = {
        'tram': tram_cua_toi, 'ds_bon': ds_bon, 
        'bon_can_canh_bao': bon_can_canh_bao, 'lich_su_ban': lich_su,
    }
    return render(request, 'staff_pos.html', context)


@login_required
def xu_ly_ban_hang(request):
    if request.method == 'POST':
        if request.user.role == 'admin' or request.user.is_superuser:
             messages.error(request, "Giám đốc không có quyền thực hiện bán hàng!")
             return redirect('admin_dashboard')

        if not request.user.tram_xang:
            messages.error(request, "Lỗi bảo mật: Bạn không thuộc trạm xăng nào!")
            return redirect('staff_pos')

        try:
            # Lấy thông tin từ form
            loai_nl = request.POST.get('loai_nhien_lieu')
            so_tien = float(request.POST.get('so_tien'))
            
            # Tính toán dựa trên giá thực tế DB
            gia_db = BangGiaNhienLieu.objects.filter(loai_nhien_lieu=loai_nl).first()
            don_gia = gia_db.gia_ban if gia_db else 20000
            so_lit = so_tien / don_gia

            # Bắt đầu giao dịch an toàn
            with transaction.atomic(): 
                bon = BonChua.objects.select_for_update().get(
                    tram=request.user.tram_xang, 
                    loai_nhien_lieu=loai_nl
                )
            
                if bon.muc_hien_tai >= so_lit:
                    bon.muc_hien_tai -= so_lit
                    bon.save()
                    
                    ma_hd_moi = f"HD-{timezone.now().strftime('%y%m%d%H%M%S')}-{request.user.id}"
                    hd = HoaDon.objects.create(
                        ma_hd=ma_hd_moi,
                        nhan_vien=request.user,
                        tong_tien=so_tien
                    )
                    
                    ChiTietHoaDon.objects.create(
                        hoa_don=hd,
                        ten_mat_hang=f"Nhiên liệu {loai_nl}",
                        so_luong=so_lit,
                        don_gia=don_gia,
                        thanh_tien=so_tien
                    )
                    
                    messages.success(request, f"Thanh toán thành công: {so_lit:.2f} Lít {loai_nl}!")
                else:
                    messages.error(request, "Bồn không đủ nhiên liệu để xuất!")
                    
        except Exception as e:
            logger.error(f"Lỗi bán hàng: {str(e)}")
            messages.error(request, "Có lỗi xảy ra, vui lòng thử lại!")
            
    return redirect('staff_pos')


@login_required
def staff_chot_ca(request):
    today = timezone.now().date()
    ds_hoa_don = HoaDon.objects.filter(nhan_vien=request.user, thoi_gian__date=today)
    tong_tien = ds_hoa_don.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0
    so_gd = ds_hoa_don.count()
    tong_lit = ChiTietHoaDon.objects.filter(hoa_don__in=ds_hoa_don).aggregate(Sum('so_luong'))['so_luong__sum'] or 0

    return render(request, 'staff_chot_ca.html', {
        'tong_tien': tong_tien, 'so_gd': so_gd, 
        'tong_lit': tong_lit, 'ngay_chot': timezone.now()
    })
@login_required
def tao_yeu_cau_nhap_hang(request):
    if request.method == 'POST':
        # Chỉ Trưởng trạm mới được phép xin xăng
        if request.user.role != 'tram_truong':
            messages.error(request, "Chỉ Cửa hàng trưởng mới có quyền yêu cầu cấp hàng!")
            return redirect('staff_pos')

        tram = request.user.tram_xang
        if not tram:
            messages.error(request, "Lỗi: Trạm xăng của bạn chưa được xác định!")
            return redirect('staff_pos')

        try:
            loai_nl = request.POST.get('loai_nhien_lieu')
            so_luong = request.POST.get('so_luong')
            ghi_chu = request.POST.get('ghi_chu', '') # Ghi chú có thể để trống

            # Import model Yêu Cầu (tên model có thể khác tùy bạn đặt trong models.py)
            from .models import YeuCauNhapHang 
            
            # Tạo bản ghi mới vào Database
            YeuCauNhapHang.objects.create(
                tram=tram,
                loai_nhien_lieu=loai_nl,
                so_luong=float(so_luong),
                ghi_chu=ghi_chu,
                trang_thai='cho_duyet' # Mặc định là chờ Admin duyệt
            )
            
            messages.success(request, f"Đã gửi lệnh xin cấp {so_luong} Lít {loai_nl} lên Tổng công ty thành công!")
        except Exception as e:
            messages.error(request, f"Lỗi khi tạo yêu cầu: {e}")

    return redirect('staff_pos')
# ==========================================
# CÁC HÀM CÒN LẠI (GIỮ NGUYÊN HOÀN TOÀN)
# ==========================================
def guest_home(request):
    # 1. LẤY BANNER ĐỘNG (Cái nào đang bật thì lấy ra)
    banner_active = BannerTrangChu.objects.filter(dang_hien_thi=True).first()

    # 2. LẤY TIN TỨC & SẢN PHẨM MỚI NHẤT
    tin_tuc_moi = TinTuc.objects.order_by('-ngay_dang')[:3]
    san_pham_hot = SanPham.objects.all()[:4]
    
    # 3. XỬ LÝ DỮ LIỆU BẢN ĐỒ GIS CHO TRẠM XĂNG
    trams = TramXang.objects.all()
    tram_list = []
    for t in trams:
        available_fuels = []
        # Kiểm tra bồn chứa của trạm đó xem còn loại xăng nào
        if BonChua.objects.filter(tram=t, loai_nhien_lieu='A95', muc_hien_tai__gt=0).exists(): available_fuels.append('A95')
        if BonChua.objects.filter(tram=t, loai_nhien_lieu='E5', muc_hien_tai__gt=0).exists(): available_fuels.append('E5')
        if BonChua.objects.filter(tram=t, loai_nhien_lieu='DO', muc_hien_tai__gt=0).exists(): available_fuels.append('DO')
        if BonChua.objects.filter(tram=t, loai_nhien_lieu='E10', muc_hien_tai__gt=0).exists(): available_fuels.append('E10')

        tram_list.append({
            'id': t.id, 'ten': t.ten_tram, 'lat': t.latitude, 'lng': t.longitude,
            'dia_chi': t.dia_chi, 'fuels': available_fuels
        })

    # 4. TỐI ƯU HÓA LẤY GIÁ NHIÊN LIỆU (Chỉ gọi DB 1 lần duy nhất)
    # Lấy tất cả giá hiện có tạo thành 1 cuốn từ điển { 'A95': 24500, 'E5': 23500... }
    gia_db = {gia.loai_nhien_lieu: gia.gia_ban for gia in BangGiaNhienLieu.objects.all()}
    
    # Dùng hàm .get() của Python: Nếu có giá trong DB thì lấy, không có thì lấy giá mặc định (fallback)
    gia_hien_tai = {
        'A95': gia_db.get('A95', 24500),
        'E5':  gia_db.get('E5', 23500),
        'E10': gia_db.get('E10', 24000),
        'DO':  gia_db.get('DO', 21000),
    }

    # 5. GÓI DỮ LIỆU VÀ ĐẨY RA GIAO DIỆN
    context = {
        'banner': banner_active,        # Đã thêm biến banner
        'tin_tuc': tin_tuc_moi,
        'san_pham': san_pham_hot,
        'tram_json': json.dumps(tram_list),
        'gia': gia_hien_tai
    }
    
    return render(request, 'index.html', context)

def trang_gioi_thieu(request): return render(request, 'pages/gioi_thieu.html')
from django.http import Http404

def chi_tiet_linh_vuc(request, slug):
    # Kho dữ liệu nội dung cho 5 lĩnh vực
    data = {
        'kinh-doanh-xang-dau': {
            'title': 'Kinh Doanh Xăng Dầu',
            'img': '/static/images/banners/kinh-doanh-xang-dau.jpg',
            'content': 'Với hơn 500 trạm phân phối trên toàn quốc, GSMS tự hào là nhà cung cấp nhiên liệu sạch (Euro 5) hàng đầu, đảm bảo nguồn cung ổn định 24/7 cho mọi nhu cầu dân dụng và công nghiệp.',
            'cam_ket': [
                '100% Nhiên liệu đạt chuẩn khí thải Euro 5.',
                'Đo lường chính xác từng giọt bằng trụ bơm điện tử.',
                'Thanh toán linh hoạt qua POS, Thẻ tín dụng, và QRCode.'
            ]
        },
        'van-tai-xang-dau': {
            'title': 'Vận Tải Xăng Dầu',
            'img': '/static/images/banners/van-tai-xang-dau.jpg', # Có thể thay link ảnh khác
            'content': 'Đội xe bồn hiện đại được trang bị hệ thống giám sát hành trình GIS và cảm biến an toàn, cam kết vận chuyển nhiên liệu an toàn, đúng hẹn đến mọi miền tổ quốc.',
            'cam_ket': [
                'Đội xe bồn từ 10m3 đến 40m3 đáp ứng mọi địa hình.',
                'Giám sát lộ trình và nhiệt độ bồn chứa theo thời gian thực (Real-time).',
                'Tuân thủ tuyệt đối quy định PCCC và an toàn môi trường.'
            ]
        },
        'khi-hoa-long': {
            'title': 'Khí Hóa Lỏng (LPG)',
            'img': '/static/images/khi_hoa_long.jpg', # Có thể thay link ảnh khác
            'content': 'Cung cấp hệ thống Khí dầu mỏ hóa lỏng (LPG) cho bếp ăn công nghiệp, nhà máy sản xuất và hệ thống dân dụng với ngọn lửa xanh, nhiệt lượng cao và an toàn tuyệt đối.',
            'cam_ket': [
                'Chất lượng gas tinh khiết, không tạp chất, thân thiện môi trường.',
                'Thiết kế, thi công và bảo trì hệ thống bồn chứa gas công nghiệp.',
                'Bảo hiểm trách nhiệm lên đến hàng tỷ đồng cho mỗi bình gas.'
            ]
        },
        'hoa-dau-dung-moi': {
            'title': 'Hóa Dầu & Dung Môi',
            'img': '/static/images/banners/hoa-dau-dung-moi.jpg', # Có thể thay link ảnh khác
            'content': 'Cung cấp các sản phẩm hóa dầu cao cấp như dầu nhờn bôi trơn, nhựa đường, và các dung môi chuyên dụng phục vụ cho ngành công nghiệp sản xuất và xây dựng.',
            'cam_ket': [
                'Dầu nhờn thế hệ mới, kéo dài tuổi thọ động cơ gấp 2 lần.',
                'Nhựa đường chất lượng cao phục vụ các siêu dự án giao thông.',
                'Hỗ trợ kiểm định và tư vấn kỹ thuật hóa dầu miễn phí.'
            ]
        },
        'dich-vu-tai-chinh': {
            'title': 'Dịch Vụ Tài Chính',
            'img': '/static/images/banners/dich-vu-tai-chinh.jpg', # Có thể thay link ảnh khác
            'content': 'Hệ sinh thái thanh toán không tiền mặt và giải pháp tài chính linh hoạt dành riêng cho các doanh nghiệp vận tải và khách hàng thân thiết của GSMS.',
            'cam_ket': [
                'Phát hành Thẻ doanh nghiệp (Fleet Card) quản lý định mức xăng dầu đổ hàng tháng.',
                'Hỗ trợ cấp hạn mức công nợ lên đến 30 ngày cho đối tác chiến lược.',
                'Bảo hiểm xe cơ giới và bảo hiểm hàng hóa ưu đãi.'
            ]
        }
    }

    # Lấy dữ liệu dựa trên slug trên URL
    context = data.get(slug)
    
    # Nếu người dùng gõ link bậy bạ không có trong 5 cái trên -> Báo lỗi 404
    if not context:
        raise Http404("Không tìm thấy lĩnh vực này")
        
    return render(request, 'pages/linh_vuc.html', context)

def trang_tin_tuc(request): return render(request, 'pages/tin_tuc.html', {'ds_tin': TinTuc.objects.all().order_by('-ngay_dang')})
def trang_san_pham(request): return render(request, 'pages/san_pham.html', {'ds_sp': SanPham.objects.all()})
def trang_lien_he(request):
    if request.method == 'POST':
        ho_ten = request.POST.get('ho_ten')
        email_khach = request.POST.get('email')
        tieu_de = request.POST.get('tieu_de')
        noi_dung = request.POST.get('noi_dung')
        noidung_email = f"Thông tin người gửi:\n- Tên: {ho_ten}\n- Email: {email_khach}\nNội dung:\n{noi_dung}"
        try:
            send_mail(f"[Website Liên Hệ] {tieu_de}", noidung_email, settings.DEFAULT_FROM_EMAIL, ['admin@gsms.com'], fail_silently=False)
            messages.success(request, "Đã gửi thông điệp!")
        except Exception as e: messages.error(request, f"Lỗi gửi email: {e}")
        return redirect('lien_he')
    return render(request, 'pages/lien_he.html')

def tao_du_lieu_mau(request):
    messages.error(request, "Chức năng Reset dữ liệu đã bị khóa để bảo vệ hệ thống!")
    return redirect('admin_dashboard')

@login_required
def bao_cao_tram(request):
    user = request.user
    
    # NẾU LÀ GIÁM ĐỐC LẠC VÀO ĐÂY, ĐƯA VỀ DASHBOARD
    if user.role == 'admin' or user.is_superuser:
        return redirect('admin_dashboard')
    
    if user.role != 'tram_truong':
        messages.error(request, "Lỗi bảo mật: Chỉ Cửa hàng trưởng mới có quyền xem Báo cáo Trạm!")
        return redirect('staff_pos')
    tram = request.user.tram_xang
    if not tram:
        return redirect('staff_pos')

    today = timezone.now().date()
    hds_hom_nay = HoaDon.objects.filter(nhan_vien__tram_xang=tram, thoi_gian__date=today)
    doanh_thu_nhan_vien = HoaDon.objects.filter(nhan_vien__tram_xang=tram, thoi_gian__date=today).values('nhan_vien__username', 'nhan_vien__full_name').annotate(tong_ban=Sum('tong_tien'), so_don=Count('id')).order_by('-tong_ban')

    return render(request, 'bao_cao_tram.html', {
        'tram': tram, 'ngay_bao_cao': timezone.now(),
        'doanh_thu_hom_nay': hds_hom_nay.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0,
        'so_gd_hom_nay': hds_hom_nay.count(),
        'san_luong_hom_nay': ChiTietHoaDon.objects.filter(hoa_don__in=hds_hom_nay).aggregate(Sum('so_luong'))['so_luong__sum'] or 0,
        'ds_bon': BonChua.objects.filter(tram=tram),
        'doanh_thu_nhan_vien': doanh_thu_nhan_vien,
    })

@login_required
def xuat_excel_doanh_thu(request):
    if request.user.role != 'admin' and not request.user.is_superuser: 
        return redirect('trang_chu')
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment
    except ImportError:
        messages.error(request, "Vui lòng cài openpyxl (pip install openpyxl)")
        return redirect('admin_dashboard')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bao_Cao_Doanh_Thu_Tram"
    ws.append(['STT', 'Tên Trạm Xăng', 'Địa Chỉ', 'Doanh Thu (VNĐ)', 'Sản Lượng (Lít)', 'Số Đơn'])
    
    tu_khoa = request.GET.get('q', '')
    ds_tram = TramXang.objects.filter(ten_tram__icontains=tu_khoa) if tu_khoa else TramXang.objects.all()
    today = timezone.now().date()
    tong_dt = 0

    for stt, t in enumerate(ds_tram, 1):
        hds = HoaDon.objects.filter(nhan_vien__tram_xang=t, thoi_gian__date=today)
        dt = hds.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0
        sl = ChiTietHoaDon.objects.filter(hoa_don__in=hds).aggregate(Sum('so_luong'))['so_luong__sum'] or 0
        tong_dt += dt
        ws.append([stt, t.ten_tram, t.dia_chi, dt, sl, hds.count()])

    ws.append(['', 'TỔNG CỘNG', '', tong_dt, '', ''])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="DoanhThu_{timezone.now().strftime("%d%m%Y")}.xlsx"'
    wb.save(response)
    return response

@login_required
def quan_ly_nhan_su(request):
    if request.user.role != 'admin' and not request.user.is_superuser: 
        messages.error(request, "Bạn không có quyền truy cập trang này!")
        return redirect('staff_pos')
    return render(request, 'quan_ly_nhan_su.html', {'ds_nhan_su': User.objects.exclude(is_superuser=True).exclude(role='admin').order_by('-date_joined'), 'ds_tram': TramXang.objects.all()})

@login_required
def thao_tac_nhan_su(request):
    if request.method == 'POST' and (request.user.role == 'admin' or request.user.is_superuser):
        action = request.POST.get('action')
        try:
            if action == 'add':
                User.objects.create_user(username=request.POST.get('username'), password=request.POST.get('password'), full_name=request.POST.get('full_name'), phone=request.POST.get('phone'), role=request.POST.get('role'), tram_xang_id=request.POST.get('tram_id'))
                messages.success(request, "Đã tạo tài khoản mới!")
            elif action == 'toggle_lock':
                nv = User.objects.get(id=request.POST.get('user_id'))
                nv.is_active = not nv.is_active
                nv.save()
            elif action == 'edit':
                nv = User.objects.get(id=request.POST.get('user_id'))
                nv.full_name = request.POST.get('full_name')
                nv.role = request.POST.get('role')
                nv.tram_xang_id = request.POST.get('tram_id')
                if request.POST.get('password'): nv.set_password(request.POST.get('password'))
                nv.save()
            elif action == 'delete':
                nv = User.objects.get(id=request.POST.get('user_id'))
                if HoaDon.objects.filter(nhan_vien=nv).exists(): messages.error(request, "Không thể xóa do đã phát sinh giao dịch.")
                else: nv.delete()
        except Exception as e: messages.error(request, f"Lỗi: {e}")
    return redirect('quan_ly_nhan_su')

@login_required
def quan_ly_gia(request):
    if request.user.role != 'admin' and not request.user.is_superuser: 
        messages.error(request, "Chỉ Giám đốc mới được điều chỉnh giá!")
        return redirect('staff_pos')
    if request.method == 'POST':
        try:
            for loai, key in [('A95', 'gia_A95'), ('E5', 'gia_E5'), ('E10', 'gia_E10'), ('DO', 'gia_DO')]:
                if request.POST.get(key): BangGiaNhienLieu.objects.update_or_create(loai_nhien_lieu=loai, defaults={'gia_ban': float(request.POST.get(key))})
            messages.success(request, "Đã đồng bộ giá!")
        except Exception as e: messages.error(request, f"Lỗi: {e}")
        return redirect('quan_ly_gia')

    gia_hien_tai = {loai: BangGiaNhienLieu.objects.filter(loai_nhien_lieu=loai).first() for loai in ['A95', 'E5', 'E10', 'DO']}
    return render(request, 'quan_ly_gia.html', {'gia_hien_tai': gia_hien_tai})
@login_required
def duyet_yeu_cau(request, yc_id):
    # Chỉ Admin mới được quyền duyệt
    if request.user.role != 'admin' and not request.user.is_superuser:
        messages.error(request, "Bạn không có quyền thao tác!")
        return redirect('trang_chu')

    try:
        from .models import YeuCauNhapHang
        yc = YeuCauNhapHang.objects.get(id=yc_id)
        
        # Đổi trạng thái thành 'da_giao' (hoặc 'hoan_thanh')
        yc.trang_thai = 'da_giao'
        yc.save()
        
        messages.success(request, f"Đã xử lý xong yêu cầu cấp hàng của {yc.tram.ten_tram}!")
    except Exception as e:
        messages.error(request, "Không tìm thấy yêu cầu này!")

    # Đá ngược lại về trang Bản đồ
    return redirect('admin_import')