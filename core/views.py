import json
from urllib import request
import uuid
import random
import string
import logging
from datetime import timedelta
import base64

from django.http import JsonResponse
from collections import defaultdict
from django.db.models import Q
from django.core.paginator import Paginator
from django.core.files.base import ContentFile
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.db import transaction
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model

# === IMPORT MODELS ===
from .models import (
    TramXang, BonChua, NhaCungCap, HoaDon, ChiTietHoaDon, 
    TinTuc, DanhMuc, SanPham, PhieuNhap, YeuCauNhapHang, BangGiaNhienLieu, BannerTrangChu, DanhMucMart, SanPhamMart, DanhGiaSanPham, DoiTacB2B, HoSoUngVien, LienHeGopY
)

User = get_user_model()
logger = logging.getLogger(__name__)

# ==========================================
# 1. HỆ THỐNG XÁC THỰC (ĐÃ NÂNG CẤP PHÂN LUỒNG)
# ==========================================
def dang_nhap(request):
    # Nếu đã đăng nhập rồi thì phân luồng đẩy thẳng vào trong luôn
    if request.user.is_authenticated:
        return phan_luong_dashboard(request.user)

    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        user = authenticate(request, username=u, password=p)
        
        if user is not None:
            if not user.is_active:
                messages.error(request, "Tài khoản của bạn đã bị khóa!")
                return redirect('login')
                
            login(request, user)
            messages.success(request, f"Xin chào {user.full_name or user.username}!")
            
            # Đẩy qua hàm phân luồng
            return phan_luong_dashboard(user)
        else:
            messages.error(request, "Tên đăng nhập hoặc mật khẩu không đúng!")
            
    return render(request, 'pages/login.html')

# --- HÀM PHỤ TRỢ: CHIA ĐƯỜNG ĐI SAU KHI ĐĂNG NHẬP ---
def phan_luong_dashboard(user):
    if user.role in ['admin', 'ke_toan'] or user.is_superuser:
        return redirect('admin_dashboard')    # Admin & Kế toán vào Dashboard Tổng
    elif user.role == 'truong_tram':
        return redirect('bao_cao_tram')       # Trưởng trạm vào trang báo cáo của trạm mình
    elif user.role == 'nv_ban_hang':
        return redirect('pos_mart')           # NV Bán hàng vào thẳng Siêu thị Mart
    elif user.role == 'nv_ban_xang':
        return redirect('pos_xang')           # NV Bơm xăng vào thẳng máy POS Bơm xăng
    else:
        return redirect('trang_chu')          # Fallback an toàn

def dang_xuat(request):
    logout(request)
    messages.info(request, "Đăng xuất thành công.")
    return redirect('login')


# ==========================================
# 2. GIAO DIỆN KHÁCH & TRANG CHỦ (PAGES)
# ==========================================
def guest_home(request):
    tin_moi_nhat = TinTuc.objects.order_by('-ngay_dang')[:3]
    san_pham_hot = SanPham.objects.all()[:4]
    
    trams = TramXang.objects.all()
    bon_chua_co_xang = BonChua.objects.filter(muc_hien_tai__gt=0).values_list('tram_id', 'loai_nhien_lieu')

    nhien_lieu_theo_tram = defaultdict(list)
    for tram_id, loai_nl in bon_chua_co_xang:
        nhien_lieu_theo_tram[tram_id].append(loai_nl)

    tram_list = []
    for t in trams:
        available_fuels = nhien_lieu_theo_tram.get(t.id, [])
        if not available_fuels:
            available_fuels = ['A95', 'E5', 'DO']
            if '10' in t.ten_tram or 'Đại Học' in t.ten_tram:
                available_fuels.append('E10')

        tram_list.append({
            'id': t.id, 'ten': t.ten_tram, 
            'lat': float(t.latitude), 'lng': float(t.longitude),
            'dia_chi': t.dia_chi, 'fuels': available_fuels
        })

    gia_db = {gia.loai_nhien_lieu: gia.gia_ban for gia in BangGiaNhienLieu.objects.all()}
    gia_hien_tai = {
        'A95': gia_db.get('A95', 24500), 'E5': gia_db.get('E5', 23500),
        'E10': gia_db.get('E10', 24000), 'DO': gia_db.get('DO', 21000),
    }

    context = {
        'tin_moi_nhat': tin_moi_nhat,
        'san_pham': san_pham_hot,
        'tram_json': json.dumps(tram_list), 
        'gia': gia_hien_tai
    }
    return render(request, 'pages/trang_chu.html', context)

def trang_gioi_thieu(request): return render(request, 'pages/gioi_thieu.html')

def trang_tin_tuc(request):
    tu_khoa = request.GET.get('q', '')
    if tu_khoa:
        ds_tin_goc = TinTuc.objects.filter(
            Q(tieu_de__icontains=tu_khoa) | Q(tom_tat__icontains=tu_khoa)
        ).order_by('-ngay_dang')
    else:
        ds_tin_goc = TinTuc.objects.all().order_by('-ngay_dang')

    paginator = Paginator(ds_tin_goc, 6) 
    page_number = request.GET.get('page')
    ds_tin = paginator.get_page(page_number)

    return render(request, 'pages/tin_tuc.html', {'ds_tin': ds_tin, 'tu_khoa': tu_khoa})

def chi_tiet_tin_tuc(request, id):
    tin = get_object_or_404(TinTuc, id=id)
    tin_lien_quan = TinTuc.objects.exclude(id=id).order_by('-ngay_dang')[:3]
    return render(request, 'pages/chi_tiet_tin_tuc.html', {'tin': tin, 'tin_lien_quan': tin_lien_quan})

def trang_san_pham(request): 
    return render(request, 'pages/san_pham.html', {'ds_sp': SanPham.objects.all()})

def chi_tiet_linh_vuc(request, slug):
    data = {
        'kinh-doanh-xang-dau': {'title': 'Kinh Doanh Xăng Dầu', 'img': '/static/images/banners/kinh-doanh-xang-dau.jpg', 'content': '...', 'cam_ket': []},
        'van-tai-xang-dau': {'title': 'Vận Tải Xăng Dầu', 'img': '/static/images/banners/van-tai-xang-dau.jpg', 'content': '...', 'cam_ket': []},
        'khi-hoa-long': {'title': 'Khí Hóa Lỏng (LPG)', 'img': '/static/images/banners/khi-hoa-long.jpg', 'content': '...', 'cam_ket': []},
        'hoa-dau-dung-moi': {'title': 'Hóa Dầu & Dung Môi', 'img': '/static/images/banners/hoa-dau-dung-moi.jpg', 'content': '...', 'cam_ket': []},
        'dich-vu-tai-chinh': {'title': 'Dịch Vụ Tài Chính', 'img': '/static/images/banners/dich-vu-tai-chinh.jpg', 'content': '...', 'cam_ket': []}
    }
    context = data.get(slug)
    if not context: raise Http404("Không tìm thấy lĩnh vực này")
    return render(request, 'pages/linh_vuc.html', context)

def trang_lien_he(request):
    if request.method == 'POST':
        ho_ten = request.POST.get('ho_ten')
        email_khach = request.POST.get('email')
        tieu_de = request.POST.get('tieu_de')
        noi_dung = request.POST.get('noi_dung')
        try:
            send_mail(f"[Website Liên Hệ] {tieu_de}", f"Từ: {ho_ten} ({email_khach})\n\n{noi_dung}", settings.DEFAULT_FROM_EMAIL, ['admin@gsms.com'], fail_silently=False)
            messages.success(request, "Đã gửi thông điệp!")
        except Exception as e: 
            messages.error(request, f"Lỗi gửi email: {e}")
        return redirect('lien_he')
    return render(request, 'pages/lien_he.html')

def trang_doi_tac(request): return render(request, 'pages/doi_tac.html')

def trang_tuyen_dung(request): return render(request, 'pages/tuyen_dung.html')


# ==========================================
# 3. NHÂN VIÊN & TRƯỞNG TRẠM (STAFF POS)
# ==========================================
@login_required
def pos_xang(request):
    user = request.user
    # Ngăn Admin & Kế toán vào màn hình POS bơm xăng
    if user.role in ['admin', 'ke_toan'] or user.is_superuser: 
        return redirect('admin_dashboard')
        
    if not user.tram_xang:
        messages.error(request, "Tài khoản của bạn chưa được phân công về Trạm Xăng nào!")
        return redirect('login')

    tram_cua_toi = user.tram_xang
    ds_bon_raw = BonChua.objects.filter(tram=tram_cua_toi)
    dict_gia = {item.loai_nhien_lieu: item.gia_ban for item in BangGiaNhienLieu.objects.all()}

    ds_bon = []
    bon_can_canh_bao = []
    for b in ds_bon_raw:
        if b.suc_chua_toi_da > 0 and (b.muc_hien_tai / b.suc_chua_toi_da) * 100 < 20:
            bon_can_canh_bao.append(b)
        b.gia_ban_hien_tai = dict_gia.get(b.loai_nhien_lieu, 20000)
        ds_bon.append(b)

    if user.role == 'truong_tram':
        lich_su = HoaDon.objects.filter(nhan_vien__tram_xang=tram_cua_toi).order_by('-thoi_gian')[:20]
    else:
        lich_su = HoaDon.objects.filter(nhan_vien=user).order_by('-thoi_gian')[:10]

    return render(request, 'staff/pos_xang.html', {
        'tram': tram_cua_toi, 
        'ds_bon': ds_bon, 
        'bon_can_canh_bao': bon_can_canh_bao, 
        'lich_su_ban': lich_su
    })

@login_required
def pos_mart(request):
    user = request.user
    if user.role in ['admin', 'ke_toan'] or user.is_superuser: 
        return redirect('admin_dashboard')
        
    if not user.tram_xang:
        messages.error(request, "Tài khoản của bạn chưa được phân công về Trạm Xăng nào!")
        return redirect('login')

    tram_cua_toi = user.tram_xang
    san_pham_mart = SanPhamMart.objects.filter(ton_kho__gt=0)

    if user.role == 'truong_tram':
        lich_su = HoaDon.objects.filter(nhan_vien__tram_xang=tram_cua_toi).order_by('-thoi_gian')[:20]
    else:
        lich_su = HoaDon.objects.filter(nhan_vien=user).order_by('-thoi_gian')[:10]

    return render(request, 'staff/pos_mart.html', {
        'tram': tram_cua_toi,
        'san_pham_mart': san_pham_mart,
        'lich_su_ban': lich_su
    })

@login_required
def xu_ly_ban_hang(request):
    if request.method == 'POST':
        if request.user.role in ['admin', 'ke_toan'] or request.user.is_superuser: 
            return redirect('admin_dashboard')
            
        try:
            loai_nl = request.POST.get('loai_nhien_lieu')
            so_tien = float(request.POST.get('so_tien'))
            gia_db = BangGiaNhienLieu.objects.filter(loai_nhien_lieu=loai_nl).first()
            don_gia = gia_db.gia_ban if gia_db else 20000
            so_lit = so_tien / don_gia

            with transaction.atomic(): 
                bon = BonChua.objects.select_for_update().get(tram=request.user.tram_xang, loai_nhien_lieu=loai_nl)
                if bon.muc_hien_tai >= so_lit:
                    bon.muc_hien_tai -= so_lit
                    bon.save()
                    
                    hd = HoaDon.objects.create(ma_hd=f"HD-{timezone.now().strftime('%y%m%d%H%M%S')}-{request.user.id}", nhan_vien=request.user, tong_tien=so_tien)
                    ChiTietHoaDon.objects.create(hoa_don=hd, ten_mat_hang=f"Nhiên liệu {loai_nl}", so_luong=so_lit, don_gia=don_gia, thanh_tien=so_tien)
                    messages.success(request, f"Thanh toán thành công: {so_lit:.2f} Lít {loai_nl}!")
                else:
                    messages.error(request, "Bồn không đủ nhiên liệu để xuất!")
        except Exception as e:
            messages.error(request, "Có lỗi xảy ra, vui lòng thử lại!")
    return redirect('pos_xang')

@login_required
def staff_chot_ca(request):
    today = timezone.now().date()
    ds_hoa_don = HoaDon.objects.filter(nhan_vien=request.user, thoi_gian__date=today)
    tong_tien = ds_hoa_don.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0
    tong_lit = ChiTietHoaDon.objects.filter(hoa_don__in=ds_hoa_don).aggregate(Sum('so_luong'))['so_luong__sum'] or 0
    
    return render(request, 'staff/staff_chot_ca.html', {'tong_tien': tong_tien, 'so_gd': ds_hoa_don.count(), 'tong_lit': tong_lit, 'ngay_chot': timezone.now()})

@login_required
def tao_yeu_cau_nhap_hang(request):
    if request.method == 'POST':
        if request.user.role != 'truong_tram': return redirect('pos_xang')
        YeuCauNhapHang.objects.create(
            tram=request.user.tram_xang,
            loai_nhien_lieu=request.POST.get('loai_nhien_lieu'),
            so_luong=float(request.POST.get('so_luong')),
            ghi_chu=request.POST.get('ghi_chu', ''),
            trang_thai='cho_duyet'
        )
        messages.success(request, "Đã gửi yêu cầu cấp hàng lên Tổng Công Ty!")
    return redirect('pos_xang')

@login_required
def bao_cao_tram(request):
    if request.user.role != 'truong_tram': return redirect('pos_xang')
    tram = request.user.tram_xang
    today = timezone.now().date()
    hds_hom_nay = HoaDon.objects.filter(nhan_vien__tram_xang=tram, thoi_gian__date=today)
    doanh_thu_nhan_vien = HoaDon.objects.filter(nhan_vien__tram_xang=tram, thoi_gian__date=today).values('nhan_vien__username', 'nhan_vien__full_name').annotate(tong_ban=Sum('tong_tien'), so_don=Count('id')).order_by('-tong_ban')
    
    return render(request, 'staff/bao_cao_tram.html', {
        'tram': tram, 'ngay_bao_cao': timezone.now(),
        'doanh_thu_hom_nay': hds_hom_nay.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0,
        'so_gd_hom_nay': hds_hom_nay.count(),
        'san_luong_hom_nay': ChiTietHoaDon.objects.filter(hoa_don__in=hds_hom_nay).aggregate(Sum('so_luong'))['so_luong__sum'] or 0,
        'ds_bon': BonChua.objects.filter(tram=tram),
        'doanh_thu_nhan_vien': doanh_thu_nhan_vien,
    })


# ==========================================
# 4. QUẢN TRỊ TỔNG QUAN (ADMIN & KẾ TOÁN)
# ==========================================
@login_required
def admin_dashboard(request):
    # Cho phép Admin và Kế toán được xem Dashboard Tài chính
    if request.user.role not in ['admin', 'ke_toan'] and not request.user.is_superuser:
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
        ln_tram = dt * 0.065
        bang_doanh_thu.append({
            'tram': t, 'doanh_thu': dt, 'loi_nhuan': ln_tram, 'san_luong': sl, 'so_don': hds.count()
        })
    bang_doanh_thu.sort(key=lambda x: x['doanh_thu'], reverse=True)

    now = timezone.now()
    
    def lay_tong_nhien_lieu(hds_queryset):
        chi_tiet = ChiTietHoaDon.objects.filter(hoa_don__in=hds_queryset).values('ten_mat_hang').annotate(tong=Sum('so_luong'))
        fuels = [0, 0, 0, 0] 
        for item in chi_tiet:
            ten = item['ten_mat_hang']
            so_luong = float(item['tong'] or 0)
            if 'A95' in ten: fuels[0] += so_luong
            elif 'E5' in ten: fuels[1] += so_luong
            elif 'E10' in ten: fuels[2] += so_luong
            elif 'DO' in ten: fuels[3] += so_luong
        return fuels

    hds_7days = HoaDon.objects.filter(thoi_gian__date__gte=now.date() - timedelta(days=6))
    day_data = {'labels': [], 'revenue': [], 'volume': [], 'fuels': lay_tong_nhien_lieu(hds_7days)}
    for i in range(6, -1, -1):
        dt = now - timedelta(days=i)
        day_data['labels'].append(dt.strftime("%d/%m"))
        hds = HoaDon.objects.filter(thoi_gian__date=dt.date())
        day_data['revenue'].append(float(hds.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0) / 1000000)
        day_data['volume'].append(float(ChiTietHoaDon.objects.filter(hoa_don__in=hds).aggregate(Sum('so_luong'))['so_luong__sum'] or 0))

    hds_28days = HoaDon.objects.filter(thoi_gian__date__gte=now.date() - timedelta(days=27))
    month_data = {'labels': ['Tuần 1', 'Tuần 2', 'Tuần 3', 'Tuần 4'], 'revenue': [0,0,0,0], 'volume': [0,0,0,0], 'fuels': lay_tong_nhien_lieu(hds_28days)}
    for i in range(28):
        dt = now - timedelta(days=i)
        week_idx = 3 - (i // 7)
        hds = HoaDon.objects.filter(thoi_gian__date=dt.date())
        month_data['revenue'][week_idx] += float(hds.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0) / 1000000
        month_data['volume'][week_idx] += float(ChiTietHoaDon.objects.filter(hoa_don__in=hds).aggregate(Sum('so_luong'))['so_luong__sum'] or 0)

    hds_year = HoaDon.objects.filter(thoi_gian__year=now.year)
    year_data = {'labels': [f'T{i}' for i in range(1, 13)], 'revenue': [0]*12, 'volume': [0]*12, 'fuels': lay_tong_nhien_lieu(hds_year)}
    for hd in hds_year:
        m_idx = hd.thoi_gian.month - 1
        year_data['revenue'][m_idx] += float(hd.tong_tien or 0) / 1000000
        sl_sum = ChiTietHoaDon.objects.filter(hoa_don=hd).aggregate(Sum('so_luong'))['so_luong__sum'] or 0
        year_data['volume'][m_idx] += float(sl_sum)

    quarter_data = {
        'labels': ['Quý 1', 'Quý 2', 'Quý 3', 'Quý 4'],
        'revenue': [sum(year_data['revenue'][0:3]), sum(year_data['revenue'][3:6]), sum(year_data['revenue'][6:9]), sum(year_data['revenue'][9:12])],
        'volume': [sum(year_data['volume'][0:3]), sum(year_data['volume'][3:6]), sum(year_data['volume'][6:9]), sum(year_data['volume'][9:12])],
        'fuels': year_data['fuels'] 
    }

    chart_data = {'day': day_data, 'month': month_data, 'quarter': quarter_data, 'year': year_data}
    
    context = {
        'ds_bon': ds_bon,
        'doanh_thu_hom_nay': doanh_thu,
        'loi_nhuan_hom_nay': loi_nhuan_hom_nay, 
        'san_luong_hom_nay': san_luong,
        'so_giao_dich': so_giao_dich,
        'chart_data_json': json.dumps(chart_data),
        'bang_doanh_thu': bang_doanh_thu,
        'tu_khoa': tu_khoa,
    }
    return render(request, 'admin/admin_dashboard.html', context)

@login_required
def admin_import(request):
    # Chỉ Admin mới được quyền nhập xuất kho tổng
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
                ncc = NhaCungCap.objects.select_for_update().get(id=ncc_id) 
                loai_nl = bon.loai_nhien_lieu
                
                ton_kho_hien_tai = getattr(ncc, f'ton_kho_{loai_nl}', 0) 
                
                if ton_kho_hien_tai < so_lit:
                    messages.error(request, f"LỖI: Kho {ncc.ten_ncc} chỉ còn {ton_kho_hien_tai:,.0f} Lít {loai_nl}. Không đủ xuất!")
                    return redirect('admin_import')

                if bon.muc_hien_tai + so_lit > bon.suc_chua_toi_da:
                    messages.error(request, f"Cảnh báo: Bồn {bon.ten_bon} không đủ sức chứa!")
                else:
                    setattr(ncc, f'ton_kho_{loai_nl}', ton_kho_hien_tai - so_lit)
                    ncc.save() 

                    bon.muc_hien_tai += so_lit
                    bon.save() 
                    
                    gia_nhap_si = 21000 
                    so_km = float(request.POST.get('khoang_cach', 0)) 
                    tien_cuoc = so_km * 15000
                    tien_hang = so_lit * gia_nhap_si

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

                    YeuCauNhapHang.objects.filter(
                        tram=bon.tram,
                        loai_nhien_lieu=loai_nl,
                        trang_thai='cho_duyet'
                    ).update(trang_thai='da_duyet')

                    messages.success(request, f"Đã xuất {so_lit:,.0f} lít từ Kho {ncc.ten_ncc} đến {bon.tram.ten_tram}.")
                    return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Lỗi nhập liệu: {e}")

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

    ds_yeu_cau = YeuCauNhapHang.objects.filter(trang_thai='cho_duyet').order_by('-id')

    context = {
        'ds_ncc': ds_ncc, 
        'ncc_json': json.dumps(ncc_list), 
        'tank_json': json.dumps(tank_list),
        'station_json': json.dumps(list(station_dict.values())), 
        'ds_yeu_cau': ds_yeu_cau,
    }
    return render(request, 'admin/admin_import.html', context)


@login_required
def duyet_yeu_cau(request, yc_id):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    try:
        yc = YeuCauNhapHang.objects.get(id=yc_id)
        yc.trang_thai = 'da_giao'
        yc.save()
        messages.success(request, f"Đã xử lý xong yêu cầu của {yc.tram.ten_tram}!")
    except: 
        messages.error(request, "Không tìm thấy yêu cầu này!")
    return redirect('admin_import')


@login_required
def quan_ly_gia(request):
    # Chỉ Admin mới được quyền set giá xăng
    if request.user.role != 'admin' and not request.user.is_superuser: 
        return redirect('trang_chu')
        
    if request.method == 'POST':
        try:
            for loai, key in [('A95', 'gia_A95'), ('E5', 'gia_E5'), ('E10', 'gia_E10'), ('DO', 'gia_DO')]:
                if request.POST.get(key): 
                    BangGiaNhienLieu.objects.update_or_create(loai_nhien_lieu=loai, defaults={'gia_ban': float(request.POST.get(key))})
            messages.success(request, "Đã đồng bộ giá cho toàn hệ thống!")
        except Exception as e: 
            messages.error(request, f"Lỗi: {e}")
        return redirect('quan_ly_gia')
        
    gia_hien_tai = {loai: BangGiaNhienLieu.objects.filter(loai_nhien_lieu=loai).first() for loai in ['A95', 'E5', 'E10', 'DO']}
    return render(request, 'admin/quan_ly_gia.html', {'gia_hien_tai': gia_hien_tai})


@login_required
def xuat_excel_doanh_thu(request):
    # Kế toán được quyền xuất Excel
    if request.user.role not in ['admin', 'ke_toan'] and not request.user.is_superuser: 
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
    
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')
    
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

    ws.append(['', 'TỔNG CỘNG TOÀN HỆ THỐNG', '', tong_dt, '', ''])
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True, color="FF0000") 
        
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="BaoCao_DoanhThu_GSMS_{timezone.now().strftime("%d%m%Y")}.xlsx"'
    wb.save(response)
    return response

def tao_du_lieu_mau(request):
    messages.error(request, "Chức năng Reset dữ liệu đã bị khóa để bảo vệ hệ thống!")
    return redirect('admin_dashboard')

# ==========================================
# 5. CRUD: TRẠM XĂNG
# ==========================================
@login_required
def admin_danh_sach_tram(request):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    ds_tram = TramXang.objects.all().order_by('-id')
    return render(request, 'admin/admin_trams.html', {'ds_tram': ds_tram})

@login_required
def admin_them_tram(request):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    
    if request.method == 'POST':
        try:
            tram = TramXang.objects.create(
                ten_tram=request.POST.get('ten_tram'), dia_chi=request.POST.get('dia_chi'),
                latitude=float(request.POST.get('latitude', 0)), longitude=float(request.POST.get('longitude', 0))
            )
            
            nhien_lieu_duoc_chon = request.POST.getlist('nhien_lieu')
            thong_so = {'A95': 15000, 'E5': 10000, 'E10': 10000, 'DO': 20000}
            for nl in nhien_lieu_duoc_chon:
                if nl in thong_so:
                    BonChua.objects.create(tram=tram, ten_bon=f"Bồn {nl}", loai_nhien_lieu=nl, suc_chua_toi_da=thong_so[nl], muc_hien_tai=0)

            p_truong = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
            p_nv = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
            
            User.objects.create_user(username=f"truongtram_{tram.id}", password=p_truong, full_name=f"Trưởng {tram.ten_tram}", role="truong_tram", tram_xang=tram)
            User.objects.create_user(username=f"nhanvien_{tram.id}", password=p_nv, full_name=f"NV {tram.ten_tram}", role="nv_ban_xang", tram_xang=tram)

            messages.success(request, f"Đã tạo Trạm! Mật khẩu Trưởng: {p_truong} | NV: {p_nv}")
            return redirect('admin_trams')
        except Exception as e:
            messages.error(request, f"Lỗi: {e}")

    return render(request, 'admin/admin_tram_form.html')

@login_required
def admin_sua_tram(request, id):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    tram = get_object_or_404(TramXang, id=id)
    
    if request.method == 'POST':
        tram.ten_tram = request.POST.get('ten_tram')
        tram.dia_chi = request.POST.get('dia_chi')
        
        lat_str = str(request.POST.get('latitude', '0')).replace(',', '.')
        lng_str = str(request.POST.get('longitude', '0')).replace(',', '.')
        
        tram.latitude = float(lat_str)
        tram.longitude = float(lng_str)
        
        tram.save()
        messages.success(request, 'Đã cập nhật thông tin Trạm xăng!')
        return redirect('admin_trams')
        
    return render(request, 'admin/admin_tram_form.html', {'tram': tram})

@login_required
def admin_xoa_tram(request, id):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    tram = get_object_or_404(TramXang, id=id)
    tram.delete()
    messages.success(request, 'Đã xóa Trạm xăng!')
    return redirect('admin_trams')

# ==========================================
# 6. CRUD: KHO TỔNG / NHÀ CUNG CẤP
# ==========================================
@login_required
def admin_danh_sach_kho(request):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    ds_kho = NhaCungCap.objects.all().order_by('-id')
    return render(request, 'admin/admin_khos.html', {'ds_kho': ds_kho})

@login_required
def admin_them_kho(request):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    if request.method == 'POST':
        NhaCungCap.objects.create(
            ten_ncc=request.POST.get('ten_ncc'), sdt=request.POST.get('sdt'), dia_chi=request.POST.get('dia_chi'),
            latitude=float(request.POST.get('latitude', 0)), longitude=float(request.POST.get('longitude', 0))
        )
        messages.success(request, "Thêm Kho tổng thành công!")
        return redirect('admin_khos')
    return render(request, 'admin/admin_kho_form.html')

@login_required
def admin_sua_kho(request, id):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    kho = get_object_or_404(NhaCungCap, id=id)
    if request.method == 'POST':
        kho.ten_ncc = request.POST.get('ten_ncc')
        kho.sdt = request.POST.get('sdt')
        kho.dia_chi = request.POST.get('dia_chi')
        kho.latitude = request.POST.get('latitude')
        kho.longitude = request.POST.get('longitude')
        kho.save()
        messages.success(request, "Cập nhật Kho thành công!")
        return redirect('admin_khos')
    return render(request, 'admin/admin_kho_form.html', {'kho': kho})

@login_required
def admin_xoa_kho(request, id):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    kho = get_object_or_404(NhaCungCap, id=id)
    kho.delete()
    messages.success(request, "Đã xóa Kho tổng!")
    return redirect('admin_khos')

# ==========================================
# 7. CRUD: NHÂN SỰ
# ==========================================
@login_required
def admin_danh_sach_nhan_su(request):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    ds_nhan_su = User.objects.exclude(is_superuser=True).exclude(role='admin').order_by('-date_joined')
    return render(request, 'admin/admin_nhan_sus.html', {'ds_nhan_su': ds_nhan_su})

@login_required
def admin_them_nhan_su(request):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    if request.method == 'POST':
        User.objects.create_user(
            username=request.POST.get('username'), password=request.POST.get('password'),
            full_name=request.POST.get('full_name'), phone=request.POST.get('phone'),
            role=request.POST.get('role'), tram_xang_id=request.POST.get('tram_id')
        )
        messages.success(request, "Tạo nhân viên mới thành công!")
        return redirect('admin_nhan_sus')
    return render(request, 'admin/admin_nhan_su_form.html', {'ds_tram': TramXang.objects.all()})

@login_required
def admin_sua_nhan_su(request, id):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    nv = get_object_or_404(User, id=id)
    if request.method == 'POST':
        nv.full_name = request.POST.get('full_name')
        nv.phone = request.POST.get('phone')
        nv.role = request.POST.get('role')
        nv.tram_xang_id = request.POST.get('tram_id')
        nv.is_active = request.POST.get('is_active') == 'on'
        
        if request.POST.get('password'): 
            nv.set_password(request.POST.get('password'))
        nv.save()
        messages.success(request, "Cập nhật nhân viên thành công!")
        return redirect('admin_nhan_sus')
    return render(request, 'admin/admin_nhan_su_form.html', {'nv': nv, 'ds_tram': TramXang.objects.all()})

@login_required
def admin_xoa_nhan_su(request, id):
    if request.user.role != 'admin' and not request.user.is_superuser: return redirect('trang_chu')
    nv = get_object_or_404(User, id=id)
    if HoaDon.objects.filter(nhan_vien=nv).exists(): 
        messages.error(request, "Không thể xóa vì nhân viên này đã xuất hóa đơn!")
    else: 
        nv.delete()
        messages.success(request, "Đã xóa nhân viên!")
    return redirect('admin_nhan_sus')

# ==========================================
# 8. CRUD: TIN TỨC
# ==========================================
@login_required
def admin_tin_tuc(request):
    if request.user.role != 'admin' and not request.user.is_superuser:
        messages.error(request, "Bạn không có quyền truy cập!")
        return redirect('trang_chu')
    
    ds_tin = TinTuc.objects.all().order_by('-ngay_dang')
    return render(request, 'admin/admin_tin_tuc.html', {'ds_tin': ds_tin})

@login_required
def admin_tin_tuc_form(request, tin_id=None):
    if request.user.role != 'admin' and not request.user.is_superuser:
        return redirect('trang_chu')

    tin_hien_tai = get_object_or_404(TinTuc, id=tin_id) if tin_id else None

    if request.method == 'POST':
        try:
            tieu_de = request.POST.get('tieu_de')
            tom_tat = request.POST.get('tom_tat')
            noi_dung = request.POST.get('noi_dung')
            anh_bia = request.FILES.get('anh_bia') 

            if not tin_hien_tai:
                tin_hien_tai = TinTuc() 

            tin_hien_tai.tieu_de = tieu_de
            tin_hien_tai.tom_tat = tom_tat
            tin_hien_tai.noi_dung = noi_dung
            
            if anh_bia: 
                tin_hien_tai.anh_bia = anh_bia

            tin_hien_tai.save()
            messages.success(request, "Lưu bài viết thành công!")
            return redirect('admin_tin_tuc')
        except Exception as e:
            messages.error(request, f"Lỗi: {e}")

    return render(request, 'admin/admin_tin_tuc_form.html', {'tin': tin_hien_tai})

@login_required
def admin_xoa_tin_tuc(request, tin_id):
    if request.user.role == 'admin' or request.user.is_superuser:
        tin = get_object_or_404(TinTuc, id=tin_id)
        tin.delete()
        messages.success(request, "Đã xóa bài viết!")
    return redirect('admin_tin_tuc')

# ==========================================
# 9. CRUD: BANNER TRANG CHỦ
# ==========================================
@login_required
def admin_banners(request):
    if request.user.role != 'admin' and not request.user.is_superuser:
        return redirect('trang_chu')
    ds_banner = BannerTrangChu.objects.all().order_by('-id')
    return render(request, 'admin/admin_banners.html', {'ds_banner': ds_banner})

@login_required
def admin_banner_form(request, banner_id=None):
    if request.user.role != 'admin' and not request.user.is_superuser:
        return redirect('trang_chu')

    banner = get_object_or_404(BannerTrangChu, id=banner_id) if banner_id else None

    if request.method == 'POST':
        tieu_de = request.POST.get('tieu_de_chinh', '')
        tieu_phu = request.POST.get('tieu_de_phu', '')
        chien_dich = request.POST.get('ten_chien_dich')
        hien_thi = request.POST.get('dang_hien_thi') == 'on'
        
        cropped_data = request.POST.get('cropped_image_base64')

        if not banner:
            banner = BannerTrangChu()

        banner.tieu_de_chinh = tieu_de
        banner.tieu_de_phu = tieu_phu
        banner.ten_chien_dich = chien_dich
        banner.dang_hien_thi = hien_thi

        if cropped_data:
            format, imgstr = cropped_data.split(';base64,')
            ext = format.split('/')[-1]
            file_name = f"banner_{uuid.uuid4().hex[:8]}.{ext}"
            banner.anh_banner = ContentFile(base64.b64decode(imgstr), name=file_name)
        else:
            file_raw = request.FILES.get('anh_banner')
            if file_raw:
                banner.anh_banner = file_raw

        banner.save()
        messages.success(request, "Đã cập nhật Banner thành công!")
        return redirect('admin_banners')

    return render(request, 'admin/admin_banner_form.html', {'banner': banner})

@login_required
def admin_xoa_banner(request, banner_id):
    if request.user.role == 'admin' or request.user.is_superuser:
        banner = get_object_or_404(BannerTrangChu, id=banner_id)
        banner.delete()
        messages.success(request, "Đã xóa Banner!")
    return redirect('admin_banners')

def gui_yeu_cau_b2b(request):
    if request.method == 'POST':
        try:
            DoiTacB2B.objects.create(
                ten_cong_ty=request.POST.get('ten_cong_ty'),
                so_dien_thoai=request.POST.get('so_dien_thoai'),
                email=request.POST.get('email'),
                nhu_cau=request.POST.get('nhu_cau')
            )
            messages.success(request, "Đã gửi yêu cầu hợp tác! Đội ngũ GSMS sẽ liên hệ với bạn sớm nhất.")
        except Exception as e:
            messages.error(request, f"Lỗi hệ thống: {e}")
    return redirect('doi_tac')

def nop_ho_so(request):
    if request.method == 'POST':
        try:
            HoSoUngVien.objects.create(
                vi_tri_ung_tuyen=request.POST.get('vi_tri'),
                ho_ten=request.POST.get('ho_ten'),
                so_dien_thoai=request.POST.get('so_dien_thoai'),
                email=request.POST.get('email'),
                file_cv=request.FILES.get('file_cv') 
            )
            messages.success(request, "Nộp hồ sơ thành công! Chúc bạn may mắn.")
        except Exception as e:
            messages.error(request, f"Lỗi nộp hồ sơ: {e}")
    return redirect('tuyen_dung')

@login_required
def admin_inbox(request):
    # Kế toán được quyền truy cập hộp thư để xử lý Hợp đồng B2B
    if request.user.role not in ['admin', 'ke_toan'] and not request.user.is_superuser:
        return redirect('trang_chu')

    if request.method == 'POST':
        loai = request.POST.get('loai')
        item_id = request.POST.get('id')
        hanh_dong = request.POST.get('hanh_dong')

        try:
            if loai == 'b2b':
                obj = DoiTacB2B.objects.get(id=item_id)
                obj.trang_thai = hanh_dong
                obj.save()
            elif loai == 'ung_vien':
                obj = HoSoUngVien.objects.get(id=item_id)
                obj.trang_thai = hanh_dong
                obj.save()
            elif loai == 'gop_y':
                obj = LienHeGopY.objects.get(id=item_id)
                obj.da_xu_ly = (hanh_dong == 'xong')
                obj.save()
            elif loai == 'danh_gia':
                obj = DanhGiaSanPham.objects.get(id=item_id)
                if hanh_dong == 'duyet':
                    obj.da_duyet = True
                    obj.save()
                elif hanh_dong == 'xoa':
                    obj.delete() 
            messages.success(request, "Đã cập nhật trạng thái thành công!")
        except Exception as e:
            messages.error(request, f"Lỗi: {e}")
        return redirect('admin_inbox')

    context = {
        'ds_b2b': DoiTacB2B.objects.all().order_by('-ngay_gui'),
        'ds_ung_vien': HoSoUngVien.objects.all().order_by('-ngay_nop'),
        'ds_gop_y': LienHeGopY.objects.all().order_by('da_xu_ly', '-ngay_gui'),
         'ds_danh_gia': DanhGiaSanPham.objects.all().order_by('da_duyet', '-ngay_gui'), 
    }
    return render(request, 'admin/admin_inbox.html', context)

@login_required
@transaction.atomic 
def xu_ly_ban_mart(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            gio_hang = data.get('gio_hang', [])
            
            if not gio_hang:
                return JsonResponse({'success': False, 'message': 'Giỏ hàng đang trống!'})

            tong_tien_hang = sum(item['gia'] * item['soLuong'] for item in gio_hang)
            tien_vat = tong_tien_hang * 0.08
            thanh_tien = tong_tien_hang + tien_vat

            ma_hd = f"MART-{uuid.uuid4().hex[:6].upper()}"
            hoa_don = HoaDon.objects.create(
                ma_hd=ma_hd,
                nhan_vien=request.user,
                tong_tien=thanh_tien
            )

            for item in gio_hang:
                sp = SanPhamMart.objects.select_for_update().get(id=item['id'])
                
                if sp.ton_kho < item['soLuong']:
                    raise ValueError(f"Mặt hàng '{sp.ten_san_pham}' không đủ tồn kho (Chỉ còn {sp.ton_kho}).")
                
                sp.ton_kho -= item['soLuong']
                sp.save()

                ChiTietHoaDon.objects.create(
                    hoa_don=hoa_don,
                    ten_mat_hang=item['ten'],
                    so_luong=item['soLuong'],
                    don_gia=item['gia'],
                    thanh_tien=item['gia'] * item['soLuong']
                )

            return JsonResponse({'success': True, 'message': 'Thanh toán thành công!', 'ma_hd': ma_hd})

        except ValueError as ve:
            return JsonResponse({'success': False, 'message': str(ve)}) 
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Lỗi hệ thống: {str(e)}'})
            
    return JsonResponse({'success': False, 'message': 'Chỉ chấp nhận phương thức POST'})

def gui_danh_gia(request, sp_id):
    if request.method == 'POST':
        try:
            sp = get_object_or_404(SanPham, id=sp_id)
            DanhGiaSanPham.objects.create(
                san_pham=sp,
                ten_khach_hang=request.POST.get('ten_khach_hang'),
                so_sao=request.POST.get('so_sao', 5), 
                noi_dung=request.POST.get('noi_dung')
            )
            messages.success(request, "Cảm ơn bạn! Đánh giá đã được gửi và đang chờ Ban quản trị kiểm duyệt.")
        except Exception as e:
            messages.error(request, f"Lỗi gửi đánh giá: {e}")
            
    return redirect(request.META.get('HTTP_REFERER', 'san_pham'))