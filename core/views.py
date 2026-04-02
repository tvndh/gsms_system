import json
import uuid
import random
from datetime import timedelta
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import TramXang, BonChua, NhaCungCap, HoaDon, ChiTietHoaDon, TinTuc, DanhMuc, SanPham, PhieuNhap
from django.contrib.auth import get_user_model
User = get_user_model()

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
            
            # --- SỬA Ở ĐÂY: Nhận diện Admin hoặc Superuser ---
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
    if request.user.role != 'admin':
        messages.warning(request, "Bạn không có quyền truy cập!")
        return redirect('staff_pos')

    today = timezone.now().date()
    ds_bon = BonChua.objects.all()

    # 1. Thống kê nhanh toàn hệ thống
    stats = HoaDon.objects.filter(thoi_gian__date=today).aggregate(
        total_money=Sum('tong_tien'), total_tx=Count('id')
    )
    doanh_thu = stats['total_money'] or 0
    so_giao_dich = stats['total_tx'] or 0
    san_luong = ChiTietHoaDon.objects.filter(hoa_don__thoi_gian__date=today).aggregate(Sum('so_luong'))['so_luong__sum'] or 0

    # ==========================================
    # 2. TÌM KIẾM & BẢNG DOANH THU TỪNG TRẠM
    # ==========================================
    tu_khoa = request.GET.get('q', '')
    ds_tram = TramXang.objects.all()
    
    if tu_khoa:
        ds_tram = ds_tram.filter(ten_tram__icontains=tu_khoa)

    bang_doanh_thu = []
    for t in ds_tram:
        hds = HoaDon.objects.filter(nhan_vien__tram_xang=t, thoi_gian__date=today)
        dt = hds.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0
        sl = ChiTietHoaDon.objects.filter(hoa_don__in=hds).aggregate(Sum('so_luong'))['so_luong__sum'] or 0
        bang_doanh_thu.append({
            'tram': t,
            'doanh_thu': dt,
            'san_luong': sl,
            'so_don': hds.count()
        })
    bang_doanh_thu.sort(key=lambda x: x['doanh_thu'], reverse=True)

    # ==========================================
    # 3. TÍNH TOÁN DỮ LIỆU BIỂU ĐỒ HOÀN CHỈNH
    # ==========================================
    now = timezone.now()
    
    # A. DỮ LIỆU THEO NGÀY (7 ngày qua)
    day_data = {'labels': [], 'revenue': [], 'volume': []}
    for i in range(6, -1, -1):
        dt = now - timedelta(days=i)
        day_data['labels'].append(dt.strftime("%d/%m"))
        hds = HoaDon.objects.filter(thoi_gian__date=dt.date())
        day_data['revenue'].append(float(hds.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0) / 1000000)
        day_data['volume'].append(float(ChiTietHoaDon.objects.filter(hoa_don__in=hds).aggregate(Sum('so_luong'))['so_luong__sum'] or 0))

    # B. DỮ LIỆU THEO THÁNG (4 tuần qua)
    month_data = {'labels': ['Tuần 1', 'Tuần 2', 'Tuần 3', 'Tuần 4'], 'revenue': [0,0,0,0], 'volume': [0,0,0,0]}
    for i in range(28):
        dt = now - timedelta(days=i)
        week_idx = 3 - (i // 7)
        hds = HoaDon.objects.filter(thoi_gian__date=dt.date())
        month_data['revenue'][week_idx] += float(hds.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0) / 1000000
        month_data['volume'][week_idx] += float(ChiTietHoaDon.objects.filter(hoa_don__in=hds).aggregate(Sum('so_luong'))['so_luong__sum'] or 0)

    # C. DỮ LIỆU THEO NĂM (12 Tháng)
    year_data = {'labels': [f'T{i}' for i in range(1, 13)], 'revenue': [0]*12, 'volume': [0]*12}
    hds_year = HoaDon.objects.filter(thoi_gian__year=now.year)
    for hd in hds_year:
        m_idx = hd.thoi_gian.month - 1
        year_data['revenue'][m_idx] += float(hd.tong_tien or 0) / 1000000
        sl_sum = ChiTietHoaDon.objects.filter(hoa_don=hd).aggregate(Sum('so_luong'))['so_luong__sum'] or 0
        year_data['volume'][m_idx] += float(sl_sum)

    # D. DỮ LIỆU THEO QUÝ (Gộp từ Năm)
    quarter_data = {
        'labels': ['Quý 1', 'Quý 2', 'Quý 3', 'Quý 4'],
        'revenue': [
            sum(year_data['revenue'][0:3]), sum(year_data['revenue'][3:6]),
            sum(year_data['revenue'][6:9]), sum(year_data['revenue'][9:12])
        ],
        'volume': [
            sum(year_data['volume'][0:3]), sum(year_data['volume'][3:6]),
            sum(year_data['volume'][6:9]), sum(year_data['volume'][9:12])
        ]
    }

    # Đóng gói toàn bộ trả về Frontend
    chart_data = {
        'day': day_data,
        'month': month_data,
        'quarter': quarter_data,
        'year': year_data
    }
    chart_data_json = json.dumps(chart_data)

    context = {
        'ds_bon': ds_bon,
        'doanh_thu_hom_nay': doanh_thu,
        'san_luong_hom_nay': san_luong,
        'so_giao_dich': so_giao_dich,
        'chart_data_json': chart_data_json,
        'bang_doanh_thu': bang_doanh_thu,
        'tu_khoa': tu_khoa,
    }
    return render(request, 'admin_dashboard.html', context)

@login_required
def admin_import(request):
    if request.user.role != 'admin':
        return redirect('trang_chu')

    # ========================================================
    # XỬ LÝ FORM NHẬP KHO (VÀ TỰ ĐỘNG ĐÓNG YÊU CẦU)
    # ========================================================
    if request.method == 'POST':
        try:
            ncc_id = request.POST.get('ncc_id')
            bon_id = request.POST.get('bon_chua')
            so_lit = float(request.POST.get('so_lit', 0))
            
            if not bon_id:
                messages.error(request, "Vui lòng chọn bồn chứa!")
                return redirect('admin_import')
                
            bon = BonChua.objects.get(id=bon_id)
            
            if bon.muc_hien_tai + so_lit > bon.suc_chua_toi_da:
                messages.error(request, f"Cảnh báo: Bồn {bon.ten_bon} không đủ sức chứa!")
            else:
                # 1. Bơm xăng vào bồn
                bon.muc_hien_tai += so_lit
                bon.save()
                
                # 2. Tạo phiếu nhập
                PhieuNhap.objects.create(
                    ma_pn=f"PN-{timezone.now().strftime('%d%m%H%M')}",
                    nha_cung_cap_id=ncc_id,
                    bon_chua=bon,
                    so_lit_nhap=so_lit,
                    thanh_tien=so_lit * 22000
                )

                # 3. TỰ ĐỘNG TÌM VÀ ĐÓNG YÊU CẦU CỦA TRẠM NÀY (Nếu có)
                from .models import YeuCauNhapHang
                YeuCauNhapHang.objects.filter(
                    tram=bon.tram,
                    loai_nhien_lieu=bon.loai_nhien_lieu,
                    trang_thai='cho_duyet'
                ).update(trang_thai='da_duyet')

                messages.success(request, f"Đã nhập {so_lit:,.0f} lít vào {bon.ten_bon}. Yêu cầu của trạm (nếu có) đã được tự động phê duyệt!")
                return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Lỗi nhập liệu: {e}")

    # ========================================================
    # LẤY DANH SÁCH YÊU CẦU ĐỂ HIỂN THỊ
    # ========================================================
    from .models import YeuCauNhapHang
    ds_yeu_cau = YeuCauNhapHang.objects.filter(trang_thai='cho_duyet').order_by('-thoi_gian')

    ds_ncc = NhaCungCap.objects.all()
    ds_bon = BonChua.objects.select_related('tram').all()

    ncc_list = [{
        'id': n.id, 'name': n.ten_ncc, 'lat': float(n.latitude or 0), 'lng': float(n.longitude or 0), 'address': n.dia_chi
    } for n in ds_ncc]

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

    context = {
        'ds_ncc': ds_ncc, 'ncc_json': json.dumps(ncc_list), 'tank_json': json.dumps(tank_list),
        'station_json': json.dumps(list(station_dict.values())), 'ds_yeu_cau': ds_yeu_cau,
    }
    return render(request, 'admin_import.html', context)

# ==========================================
# THÊM TRẠM XĂNG VÀ TỰ ĐỘNG TẠO NHÂN SỰ + BỒN CHỨA (ĐỘNG)
# ==========================================
@login_required
def admin_add_station(request):
    if request.user.role != 'admin':
        return redirect('staff_pos')

    if request.method == 'POST':
        ten_tram = request.POST.get('ten_tram')
        dia_chi = request.POST.get('dia_chi')
        lat = request.POST.get('latitude')
        lng = request.POST.get('longitude')

        if not lat or not lng:
            messages.error(request, "Lỗi: Bạn chưa click chọn vị trí trên Bản đồ!")
            return render(request, 'admin_add_station.html')

        try:
            lat = float(lat)
            lng = float(lng)

            # 1. Tạo Trạm Xăng mới
            tram_moi = TramXang.objects.create(
                ten_tram=ten_tram,
                dia_chi=dia_chi,
                latitude=lat,
                longitude=lng
            )

            # 2. TỰ ĐỘNG TẠO BỒN CHỨA DỰA TRÊN LỰA CHỌN CỦA GIÁM ĐỐC
            # Lấy danh sách các checkbox mà người dùng đã tick (Ví dụ: ['A95', 'E5', 'DO'])
            nhien_lieu_duoc_chon = request.POST.getlist('nhien_lieu')

            # Cấu hình thông số chuẩn cho từng loại bồn nếu nó được chọn xây
            thong_so_bon = {
                'A95': {'ten': 'Bồn A95', 'max': 15000},
                'E5':  {'ten': 'Bồn E5', 'max': 10000},
                'E10': {'ten': 'Bồn E10', 'max': 10000},
                'DO':  {'ten': 'Bồn DO', 'max': 20000},
            }

            # Chạy vòng lặp: Quét xem loại nào được tick thì mới tạo bồn loại đó
            for nl in nhien_lieu_duoc_chon:
                if nl in thong_so_bon:
                    BonChua.objects.create(
                        tram=tram_moi,
                        ten_bon=thong_so_bon[nl]['ten'],
                        loai_nhien_lieu=nl,
                        suc_chua_toi_da=thong_so_bon[nl]['max'],
                        muc_hien_tai=0
                    )

            # 3. Kích hoạt tính năng TỰ ĐỘNG ĐẺ TÀI KHOẢN
            from django.contrib.auth import get_user_model
            User = get_user_model()

            tk_truong = f"truongtram_{tram_moi.id}"
            User.objects.create_user(
                username=tk_truong,
                password="123",
                full_name=f"Trưởng trạm {tram_moi.id}",
                role="tram_truong",
                tram_xang=tram_moi
            )

            tk_nhanvien = f"nhanvien_{tram_moi.id}"
            User.objects.create_user(
                username=tk_nhanvien,
                password="123",
                full_name=f"Nhân viên {tram_moi.id}",
                role="staff",
                tram_xang=tram_moi
            )

            messages.success(request, f"Đã thêm [{ten_tram}]. Hệ thống đã tạo {len(nhien_lieu_duoc_chon)} bồn chứa rỗng và 2 tài khoản (MK: 123)!")
            return redirect('admin_dashboard')

        except Exception as e:
            messages.error(request, f"Lỗi chi tiết: {str(e)}")

    return render(request, 'admin_add_station.html')


# ==========================================
# 3. KHU VỰC NHÂN VIÊN (STAFF POS)
# ==========================================

@login_required
def staff_pos(request):
    user = request.user
    if user.role == 'admin':
        return redirect('admin_dashboard')

    if not user.tram_xang:
        messages.error(request, "Tài khoản của bạn chưa được phân công về Trạm Xăng nào!")
        return redirect('login')

    tram_cua_toi = user.tram_xang
    today = timezone.now().date()

    # Lấy bồn chứa và tính phần trăm để cảnh báo
    # Lấy bồn chứa và tính phần trăm để cảnh báo
    ds_bon_raw = BonChua.objects.filter(tram=tram_cua_toi)
    ds_bon = []
    bon_can_canh_bao = []

    from .models import BangGiaNhienLieu # Import Bảng giá mới

    for b in ds_bon_raw:
        # Chỉ tính nháp tỷ lệ để làm cảnh báo đỏ, KHÔNG ghi đè vào b.phan_tram nữa
        ty_le_nhap = (b.muc_hien_tai / b.suc_chua_toi_da) * 100 if b.suc_chua_toi_da > 0 else 0
        
        # Lấy giá từ Database lên gắn vào bồn
        gia_db = BangGiaNhienLieu.objects.filter(loai_nhien_lieu=b.loai_nhien_lieu).first()
        b.gia_ban_hien_tai = gia_db.gia_ban if gia_db else 20000
        
        ds_bon.append(b)
        
        # Nếu dưới 20% sức chứa -> Đưa vào danh sách báo động đỏ
        if ty_le_nhap < 20:
            bon_can_canh_bao.append(b)

    if user.role == 'tram_truong':
        lich_su = HoaDon.objects.filter(nhan_vien__tram_xang=tram_cua_toi, thoi_gian__date=today).order_by('-thoi_gian')[:20]
    else:
        lich_su = HoaDon.objects.filter(nhan_vien=user, thoi_gian__date=today).order_by('-thoi_gian')[:10]

    context = {
        'tram': tram_cua_toi,
        'ds_bon': ds_bon,
        'bon_can_canh_bao': bon_can_canh_bao, # Gửi danh sách báo động ra giao diện
        'lich_su_ban': lich_su,
    }
    return render(request, 'staff_pos.html', context)


@login_required
def xu_ly_ban_hang(request):
    if request.method == 'POST':
        if not request.user.tram_xang:
            messages.error(request, "Lỗi bảo mật: Bạn không thuộc trạm xăng nào!")
            return redirect('staff_pos')

        try:
            loai_nl = request.POST.get('loai_nhien_lieu')
            so_tien = float(request.POST.get('so_tien'))
            
            # --- ĐÃ XÓA BỎ GIÁ CỨNG, LẤY TRỰC TIẾP TỪ DATABASE ---
            from .models import BangGiaNhienLieu
            gia_db = BangGiaNhienLieu.objects.filter(loai_nhien_lieu=loai_nl).first()
            don_gia = gia_db.gia_ban if gia_db else 20000 # Nếu Admin chưa cài giá, lấy mốc an toàn là 20k
            
            so_lit = so_tien / don_gia
            # -----------------------------------------------------
            
            bon = BonChua.objects.filter(tram=request.user.tram_xang, loai_nhien_lieu=loai_nl).first()
            
            if bon and bon.muc_hien_tai >= so_lit:
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
                
                messages.success(request, f"Đã xuất {so_lit:.2f}L {loai_nl} từ {request.user.tram_xang.ten_tram}")
            else:
                messages.error(request, "Trạm của bạn đã hết loại nhiên liệu này!")
                
        except Exception as e:
            messages.error(request, f"Có lỗi xảy ra: {e}")
            
    return redirect('staff_pos')


@login_required
def staff_chot_ca(request):
    today = timezone.now().date()
    ds_hoa_don = HoaDon.objects.filter(nhan_vien=request.user, thoi_gian__date=today)
    tong_tien = ds_hoa_don.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0
    so_gd = ds_hoa_don.count()
    tong_lit = ChiTietHoaDon.objects.filter(hoa_don__in=ds_hoa_don).aggregate(Sum('so_luong'))['so_luong__sum'] or 0

    context = {
        'tong_tien': tong_tien,
        'so_gd': so_gd,
        'tong_lit': tong_lit,
        'ngay_chot': timezone.now()
    }
    return render(request, 'staff_chot_ca.html', context)


# ==========================================
# 4. KHU VỰC KHÁCH (GUEST) & TIỆN ÍCH
# ==========================================

def guest_home(request):
    tin_tuc_moi = TinTuc.objects.order_by('-ngay_dang')[:3]
    san_pham_hot = SanPham.objects.all()[:4]

    trams = TramXang.objects.all()
    tram_list = []
    
    for t in trams:
        available_fuels = []
        if BonChua.objects.filter(tram=t, loai_nhien_lieu='A95', muc_hien_tai__gt=0).exists():
            available_fuels.append('A95')
        if BonChua.objects.filter(tram=t, loai_nhien_lieu='E5', muc_hien_tai__gt=0).exists():
            available_fuels.append('E5')
        if BonChua.objects.filter(tram=t, loai_nhien_lieu='DO', muc_hien_tai__gt=0).exists():
            available_fuels.append('DO')
        if BonChua.objects.filter(tram=t, loai_nhien_lieu='E10', muc_hien_tai__gt=0).exists():
            available_fuels.append('E10')

        tram_list.append({
            'id': t.id,
            'ten': t.ten_tram,
            'lat': t.latitude,
            'lng': t.longitude,
            'dia_chi': t.dia_chi,
            'fuels': available_fuels
        })

    # Lấy giá trực tiếp từ Database cho trang chủ
    from .models import BangGiaNhienLieu
    gia_hien_tai = {
        'A95': BangGiaNhienLieu.objects.filter(loai_nhien_lieu='A95').first().gia_ban if BangGiaNhienLieu.objects.filter(loai_nhien_lieu='A95').exists() else 24500,
        'E5': BangGiaNhienLieu.objects.filter(loai_nhien_lieu='E5').first().gia_ban if BangGiaNhienLieu.objects.filter(loai_nhien_lieu='E5').exists() else 23500,
        'E10': BangGiaNhienLieu.objects.filter(loai_nhien_lieu='E10').first().gia_ban if BangGiaNhienLieu.objects.filter(loai_nhien_lieu='E10').exists() else 24000,
        'DO': BangGiaNhienLieu.objects.filter(loai_nhien_lieu='DO').first().gia_ban if BangGiaNhienLieu.objects.filter(loai_nhien_lieu='DO').exists() else 21000,
    }

    context = {
        'tram_json': json.dumps(tram_list),
        'tin_tuc': tin_tuc_moi,
        'san_pham': san_pham_hot,
        'gia': gia_hien_tai
    }
    return render(request, 'index.html', context)


def trang_gioi_thieu(request):
    return render(request, 'pages/gioi_thieu.html')


def trang_linh_vuc(request, slug):
    data = {
        'xang-dau': {
            'title': 'Kinh Doanh Xăng Dầu',
            'img': 'https://petrolimex.com.vn/public/userfiles/images/2021/T6/18062021_KV2_CH42_01.jpg',
            'content': 'GSMS sở hữu mạng lưới 500+ trạm xăng trải dài toàn quốc, cung cấp nhiên liệu chất lượng cao.'
        },
        'van-tai': {
            'title': 'Vận Tải Xăng Dầu',
            'img': 'https://image.saigondautu.com.vn/w680/Uploaded/2026/bp_cpi/2022_09_06/xang-dau-2_LDKN.jpg',
            'content': 'Đội xe bồn hiện đại 200 chiếc cùng hệ thống tàu viễn dương, đảm bảo chuỗi cung ứng không bao giờ đứt gãy.'
        },
        'gas': {
            'title': 'Khí Hóa Lỏng (LPG)',
            'img': 'https://cdn.thuvienphapluat.vn/uploads/tintuc/2022/10/28/binh-gas.jpg',
            'content': 'Cung cấp Gas dân dụng và Gas công nghiệp an toàn tuyệt đối, ngọn lửa xanh, tiết kiệm nhiên liệu.'
        },
        'hoa-dau': {
            'title': 'Hóa Dầu & Dung Môi',
            'img': 'https://vneconomy.mediacdn.vn/thumb_w/640/2023/2/14/dau-nhot-16763660334811776856525.jpg',
            'content': 'Phân phối các dòng dầu nhờn, nhựa đường và hóa chất chuyên dụng cho các ngành công nghiệp nặng.'
        },
        'tai-chinh': {
            'title': 'Dịch vụ Tài chính',
            'img': 'https://baodautu.vn/Images/chicong/2021/04/28/PG-Bank.jpg',
            'content': 'Hợp tác với các ngân hàng lớn cung cấp giải pháp thanh toán không tiền mặt, thẻ tín dụng xăng dầu.'
        }
    }
    context = data.get(slug, data['xang-dau'])
    return render(request, 'pages/linh_vuc.html', context)


def trang_tin_tuc(request):
    tin_tuc = TinTuc.objects.all().order_by('-ngay_dang')
    return render(request, 'pages/tin_tuc.html', {'ds_tin': tin_tuc})


def trang_san_pham(request):
    san_pham = SanPham.objects.all()
    return render(request, 'pages/san_pham.html', {'ds_sp': san_pham})

def trang_lien_he(request):
    if request.method == 'POST':
        ho_ten = request.POST.get('ho_ten')
        email_khach = request.POST.get('email')
        tieu_de = request.POST.get('tieu_de')
        noi_dung = request.POST.get('noi_dung')

        # Ghép nội dung email cho đẹp
        noidung_email = f"""
        Hệ thống vừa nhận được một liên hệ mới từ khách hàng!
        
        Thông tin người gửi:
        - Họ và tên: {ho_ten}
        - Email: {email_khach}
        
        Nội dung thông điệp:
        {noi_dung}
        """

        try:
            # Lệnh bắn email đi
            send_mail(
                subject=f"[Website Liên Hệ] {tieu_de}",
                message=noidung_email,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=['admin@gsms.com'], # Gửi về email của Giám đốc (Mailtrap sẽ hứng hết)
                fail_silently=False,
            )
            messages.success(request, "Cảm ơn bạn! Thông điệp đã được gửi đến ban quản trị thành công.")
        except Exception as e:
            messages.error(request, f"Rất tiếc, có lỗi xảy ra khi gửi email: {e}")

        return redirect('lien_he')

    return render(request, 'pages/lien_he.html')
# ==========================================
# 5. TIỆN ÍCH DEV (TẠO DATA MẪU)
# ==========================================

def tao_du_lieu_mau(request):
    # KHÓA CHỨC NĂNG KHI CHẠY THỰC TẾ ĐỂ BẢO VỆ POSTGRESQL
    messages.error(request, "Lỗi: Chức năng Reset dữ liệu đã bị khóa trên hệ thống thật để bảo vệ an toàn dữ liệu!")
    return redirect('admin_dashboard')

    # ... (Toàn bộ phần code delete() và create() bên dưới kệ nó, 
    # vì có chữ return ở trên rồi nên code bên dưới sẽ không bao giờ chạy được nữa).

    PhieuNhap.objects.all().delete()
    ChiTietHoaDon.objects.all().delete()
    HoaDon.objects.all().delete()
    BonChua.objects.all().delete()
    NhaCungCap.objects.all().delete()
    TramXang.objects.all().delete()
    TinTuc.objects.all().delete()
    SanPham.objects.all().delete()
    DanhMuc.objects.all().delete()

    danh_sach_tram = [
        {"ten": "CHXD Số 1 - Trung Tâm", "dia_chi": "123 Nguyễn Huệ, Quận 1", "lat": 10.776019, "lng": 106.701124},
        {"ten": "CHXD Petrolimex Số 02", "dia_chi": "281 Lý Thường Kiệt, Quận 11", "lat": 10.775263, "lng": 106.653457},
        {"ten": "Trạm Xăng Comeco Hàng Xanh", "dia_chi": "Ngã tư Hàng Xanh, Bình Thạnh", "lat": 10.801538, "lng": 106.711124},
        {"ten": "CHXD Số 4 - Lê Văn Sỹ", "dia_chi": "380 Lê Văn Sỹ, Tân Bình", "lat": 10.792557, "lng": 106.663185},
        {"ten": "Trạm Xăng Dầu Số 5", "dia_chi": "117 Quang Trung, Gò Vấp", "lat": 10.828854, "lng": 106.678453},
        {"ten": "CHXD Comeco Lý Thái Tổ", "dia_chi": "49 Lý Thái Tổ, Quận 10", "lat": 10.765620, "lng": 106.676648},
        {"ten": "Trạm Xăng Phú Mỹ Hưng", "dia_chi": "15B Nguyễn Lương Bằng, Quận 7", "lat": 10.725801, "lng": 106.721453},
        {"ten": "CHXD An Sương", "dia_chi": "Ngã tư An Sương, Quận 12", "lat": 10.833111, "lng": 106.613322},
        {"ten": "Trạm Xăng 99 Bình Chánh", "dia_chi": "99 Nguyễn Văn Linh, Bình Chánh", "lat": 10.718843, "lng": 106.650231},
        {"ten": "CHXD Kha Vạn Cân", "dia_chi": "200 Kha Vạn Cân, TP. Thủ Đức", "lat": 10.835421, "lng": 106.748342},
        {"ten": "Trạm Xăng Hoàng Văn Thụ", "dia_chi": "200 Hoàng Văn Thụ, Phú Nhuận", "lat": 10.800010, "lng": 106.671092},
        {"ten": "CHXD Đại Lộ Đông Tây", "dia_chi": "Võ Văn Kiệt, Quận 5", "lat": 10.751245, "lng": 106.666320},
        {"ten": "Trạm Xăng Bình Tân", "dia_chi": "Quốc Lộ 1A, Bình Tân", "lat": 10.738092, "lng": 106.598211},
        {"ten": "CHXD Khu Công Nghệ Cao", "dia_chi": "88 Lê Văn Việt, TP. Thủ Đức", "lat": 10.844356, "lng": 106.782103},
        {"ten": "Trạm Xăng Nguyễn Văn Cừ", "dia_chi": "Nguyễn Văn Cừ, Quận 8", "lat": 10.758923, "lng": 106.682310},
    ]

    for index, data in enumerate(danh_sach_tram):
        tram = TramXang.objects.create(
            ten_tram=data["ten"],
            dia_chi=data["dia_chi"],
            latitude=data["lat"],
            longitude=data["lng"]
        )
        if index == 0:
            BonChua.objects.create(tram=tram, ten_bon="Bồn A95", loai_nhien_lieu='A95', suc_chua_toi_da=15000, muc_hien_tai=12000)
            BonChua.objects.create(tram=tram, ten_bon="Bồn E5", loai_nhien_lieu='E5', suc_chua_toi_da=10000, muc_hien_tai=500)
            BonChua.objects.create(tram=tram, ten_bon="Bồn DO", loai_nhien_lieu='DO', suc_chua_toi_da=20000, muc_hien_tai=18000)
        else:
            BonChua.objects.create(tram=tram, ten_bon="Bồn A95", loai_nhien_lieu='A95', suc_chua_toi_da=15000, muc_hien_tai=random.randint(1000, 15000))
            BonChua.objects.create(tram=tram, ten_bon="Bồn E5", loai_nhien_lieu='E5', suc_chua_toi_da=10000, muc_hien_tai=random.randint(0, 10000))
            BonChua.objects.create(tram=tram, ten_bon="Bồn DO", loai_nhien_lieu='DO', suc_chua_toi_da=20000, muc_hien_tai=random.randint(2000, 20000))

    NhaCungCap.objects.create(ten_ncc="Kho Xăng Dầu Nhà Bè", dia_chi="Huyện Nhà Bè", sdt="0283873888", latitude=10.668820, longitude=106.745672)
    NhaCungCap.objects.create(ten_ncc="Tổng Kho Thủ Đức", dia_chi="TP. Thủ Đức", sdt="0283731234", latitude=10.849506, longitude=106.772596)
    NhaCungCap.objects.create(ten_ncc="Kho Nhiên Liệu Bình Chánh", dia_chi="Bình Chánh", sdt="0909123456", latitude=10.730104, longitude=106.613254)
    NhaCungCap.objects.create(ten_ncc="Kho Cảng Cát Lái", dia_chi="Cát Lái, Q2", sdt="0918777999", latitude=10.771661, longitude=106.791583)

    TinTuc.objects.create(tieu_de="Giá xăng giảm mạnh chiều nay", anh_bia="https://cafefcdn.com/thumb_w/650/2033/1/4/photo-1-16728189874452093774880.jpg", tom_tat="Liên Bộ Công Thương - Tài chính vừa điều chỉnh giá xăng dầu...", noi_dung="...")
    TinTuc.objects.create(tieu_de="Khai trương trạm sạc xe điện", anh_bia="https://vinfastauto.com/sites/default/files/styles/news_detail/public/2021-04/VinFast-vf-e34_0.jpg", tom_tat="GSMS hợp tác lắp đặt trạm sạc nhanh...", noi_dung="...")
    
    dm1 = DanhMuc.objects.create(ten_dm="Dầu Nhớt")
    dm2 = DanhMuc.objects.create(ten_dm="Phụ Gia")
    SanPham.objects.create(danh_muc=dm1, ten_sp="Castrol Power 1", gia_tham_khao=120000, anh_sp="https://cf.shopee.vn/file/49a6224168e3708304f5533139855584", mo_ta="Dầu nhớt tổng hợp toàn phần")
    SanPham.objects.create(danh_muc=dm2, ten_sp="Nước làm mát", gia_tham_khao=50000, anh_sp="https://bizweb.dktcdn.net/100/416/542/products/nuoc-lam-mat-dong-co-o-to-xe-may-mau-xanh-blue-fobe-super-coolant-500ml-lon-p523a1.jpg", mo_ta="Giải nhiệt động cơ")

    # ===================================================================
    # 5. TẠO DỮ LIỆU HÓA ĐƠN LỊCH SỬ TRONG 365 NGÀY QUA
    # ===================================================================
    now = timezone.now()
    bang_gia = {'A95': 24500, 'E5': 23500, 'DO': 21000}
    loai_list = ['A95', 'E5', 'DO']
    
    for i in range(365):
        fake_date = now - timedelta(days=i)
        so_khach_trong_ngay = random.randint(2, 6)
        
        for j in range(so_khach_trong_ngay):
            loai_nl = random.choice(loai_list)
            don_gia = bang_gia[loai_nl]
            so_lit = random.uniform(20, 150)
            tong_tien = so_lit * don_gia
            
            hd = HoaDon.objects.create(
                ma_hd=f"HD-{str(uuid.uuid4())[:8].upper()}",
                nhan_vien=request.user, 
                tong_tien=tong_tien
            )
            HoaDon.objects.filter(id=hd.id).update(thoi_gian=fake_date)
            
            ChiTietHoaDon.objects.create(
                hoa_don=hd,
                ten_mat_hang=f"Xăng {loai_nl}",
                so_luong=so_lit,
                don_gia=don_gia,
                thanh_tien=tong_tien
            )

   # ===================================================================
    # 6. TẠO TÀI KHOẢN NHÂN VIÊN CHO 3 TRẠM XĂNG ĐỂ TEST PHÂN QUYỀN
    # ===================================================================
    cac_tram = TramXang.objects.all()

    if cac_tram.count() >= 3:
        # Xóa các tài khoản cũ để không bị lỗi trùng lặp khi bấm Reset nhiều lần
        User.objects.filter(username__in=[
            'truongtram1', 'nhanvien1',
            'truongtram2', 'nhanvien2',
            'truongtram3', 'nhanvien3'
        ]).delete()

        # --- TRẠM SỐ 1 ---
        tram_1 = cac_tram[0]
        User.objects.create_user(username='truongtram1', password='123', full_name='Trưởng Trạm Một', phone='0909111001', role='tram_truong', tram_xang=tram_1)
        User.objects.create_user(username='nhanvien1', password='123', full_name='Nhân Viên Một', phone='0909111002', role='staff', tram_xang=tram_1)

        # --- TRẠM SỐ 2 ---
        tram_2 = cac_tram[1]
        User.objects.create_user(username='truongtram2', password='123', full_name='Trưởng Trạm Hai', phone='0909222001', role='tram_truong', tram_xang=tram_2)
        User.objects.create_user(username='nhanvien2', password='123', full_name='Nhân Viên Hai', phone='0909222002', role='staff', tram_xang=tram_2)

        # --- TRẠM SỐ 3 ---
        tram_3 = cac_tram[2]
        User.objects.create_user(username='truongtram3', password='123', full_name='Trưởng Trạm Ba', phone='0909333001', role='tram_truong', tram_xang=tram_3)
        User.objects.create_user(username='nhanvien3', password='123', full_name='Nhân Viên Ba', phone='0909333002', role='staff', tram_xang=tram_3)

    # ĐÂY LÀ DÒNG BÁO THÀNH CÔNG VÀ CHUYỂN TRANG CUỐI CÙNG (CỰC KỲ QUAN TRỌNG)
    messages.success(request, "Đã khởi tạo 15 Trạm Xăng, 4 Kho hàng, dữ liệu mẫu và 6 Tài khoản nhân viên test thành công!")
    return redirect('admin_dashboard')

@login_required
def bao_cao_tram(request):
    user = request.user
    
    # Chỉ Trạm trưởng mới được xem
    if user.role != 'tram_truong':
        messages.error(request, "Lỗi bảo mật: Chỉ Cửa hàng trưởng mới có quyền xem Báo cáo Trạm!")
        return redirect('staff_pos')

    tram = user.tram_xang
    if not tram:
        messages.error(request, "Tài khoản của bạn chưa gắn với Trạm nào!")
        return redirect('staff_pos')

    today = timezone.now().date()
    
    # 1. Thống kê Doanh thu & Sản lượng của TẤT CẢ nhân viên trong trạm (Hôm nay)
    hds_hom_nay = HoaDon.objects.filter(nhan_vien__tram_xang=tram, thoi_gian__date=today)
    doanh_thu_hom_nay = hds_hom_nay.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0
    so_gd_hom_nay = hds_hom_nay.count()
    
    san_luong_hom_nay = ChiTietHoaDon.objects.filter(hoa_don__in=hds_hom_nay).aggregate(Sum('so_luong'))['so_luong__sum'] or 0

    # 2. Thống kê Tồn kho hiện tại của Trạm
    ds_bon = BonChua.objects.filter(tram=tram)

    # 3. Danh sách nhân viên và doanh thu từng người trong ngày
    doanh_thu_nhan_vien = HoaDon.objects.filter(
        nhan_vien__tram_xang=tram, thoi_gian__date=today
    ).values('nhan_vien__username', 'nhan_vien__full_name').annotate(
        tong_ban=Sum('tong_tien'),
        so_don=Count('id')
    ).order_by('-tong_ban')

    context = {
        'tram': tram,
        'ngay_bao_cao': timezone.now(),
        'doanh_thu_hom_nay': doanh_thu_hom_nay,
        'so_gd_hom_nay': so_gd_hom_nay,
        'san_luong_hom_nay': san_luong_hom_nay,
        'ds_bon': ds_bon,
        'doanh_thu_nhan_vien': doanh_thu_nhan_vien,
    }
    return render(request, 'bao_cao_tram.html', context)

# --- LOGIC GỬI VÀ DUYỆT YÊU CẦU NHẬP HÀNG ---
@login_required
def tao_yeu_cau_nhap(request):
    if request.method == 'POST' and request.user.role == 'tram_truong':
        loai_nl = request.POST.get('loai_nl')
        so_luong = request.POST.get('so_luong')
        ghi_chu = request.POST.get('ghi_chu', '')
        
        from .models import YeuCauNhapHang
        YeuCauNhapHang.objects.create(
            tram=request.user.tram_xang,
            nguoi_yeu_cau=request.user,
            loai_nhien_lieu=loai_nl,
            so_luong=so_luong,
            ghi_chu=ghi_chu
        )
        messages.success(request, f"Đã gửi yêu cầu cấp {so_luong}L {loai_nl} lên Giám đốc thành công!")
    return redirect('bao_cao_tram')

@login_required
def duyet_yeu_cau(request, req_id):
    if request.user.role == 'admin':
        from .models import YeuCauNhapHang
        yeu_cau = YeuCauNhapHang.objects.get(id=req_id)
        yeu_cau.trang_thai = 'da_duyet'
        yeu_cau.save()
        messages.success(request, f"Đã duyệt lệnh xuất hàng cho {yeu_cau.tram.ten_tram}! Vui lòng lập lộ trình GIS.")
    return redirect('admin_import')

@login_required
def xuat_excel_doanh_thu(request):
    if request.user.role != 'admin':
        return redirect('trang_chu')

    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment
    except ImportError:
        messages.error(request, "Hệ thống chưa cài đặt thư viện Excel. Vui lòng mở Terminal gõ lệnh: pip install openpyxl")
        return redirect('admin_dashboard')

    # 1. Tạo file Excel mới
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bao_Cao_Doanh_Thu_Tram"

    # 2. Định dạng Tiêu đề bảng
    headers = ['STT', 'Tên Trạm Xăng', 'Địa Chỉ', 'Doanh Thu Hôm Nay (VNĐ)', 'Sản Lượng (Lít)', 'Số Đơn Hàng']
    ws.append(headers)
    
    for col in range(1, 7):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = openpyxl.styles.PatternFill(start_color="198754", end_color="198754", fill_type="solid")
        cell.alignment = Alignment(horizontal='center')

    # Độ rộng cột
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 40
    ws.column_dimensions['D'].width = 20
    ws.column_dimensions['E'].width = 20

    # 3. Lấy dữ liệu theo từ khóa tìm kiếm (Giống hệt trên giao diện)
    tu_khoa = request.GET.get('q', '')
    ds_tram = TramXang.objects.all()
    if tu_khoa:
        ds_tram = ds_tram.filter(ten_tram__icontains=tu_khoa)

    today = timezone.now().date()
    tong_dt = 0

    # 4. Đổ dữ liệu vào file Excel
    for stt, t in enumerate(ds_tram, 1):
        hds = HoaDon.objects.filter(nhan_vien__tram_xang=t, thoi_gian__date=today)
        dt = hds.aggregate(Sum('tong_tien'))['tong_tien__sum'] or 0
        sl = ChiTietHoaDon.objects.filter(hoa_don__in=hds).aggregate(Sum('so_luong'))['so_luong__sum'] or 0
        sd = hds.count()
        tong_dt += dt

        ws.append([stt, t.ten_tram, t.dia_chi, dt, sl, sd])

    # Thêm dòng Tổng cộng
    ws.append(['', 'TỔNG CỘNG', '', tong_dt, '', ''])
    ws.cell(row=ws.max_row, column=2).font = Font(bold=True, color="FF0000")
    ws.cell(row=ws.max_row, column=4).font = Font(bold=True, color="FF0000")

    # 5. Đóng gói file và Gửi cho người dùng tải về
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="DoanhThu_{timezone.now().strftime("%d%m%Y")}.xlsx"'
    wb.save(response)
    
    return response
# ==========================================
# QUẢN LÝ NHÂN SỰ (Dành cho Giám Đốc)
# ==========================================
@login_required
def quan_ly_nhan_su(request):
    if request.user.role != 'admin':
        messages.error(request, "Bạn không có quyền truy cập trang này!")
        return redirect('staff_pos')

    # Chỉ lấy tài khoản nhân viên và trạm trưởng (Loại trừ admin)
    ds_nhan_su = User.objects.exclude(is_superuser=True).exclude(role='admin').order_by('-date_joined')
    ds_tram = TramXang.objects.all()

    context = {
        'ds_nhan_su': ds_nhan_su,
        'ds_tram': ds_tram,
    }
    return render(request, 'quan_ly_nhan_su.html', context)

@login_required
def thao_tac_nhan_su(request):
    if request.method == 'POST' and request.user.role == 'admin':
        action = request.POST.get('action')
        
        try:
            # 1. THÊM MỚI NHÂN VIÊN
            if action == 'add':
                User.objects.create_user(
                    username=request.POST.get('username'),
                    password=request.POST.get('password'),
                    full_name=request.POST.get('full_name'),
                    phone=request.POST.get('phone'),
                    role=request.POST.get('role'),
                    tram_xang_id=request.POST.get('tram_id')
                )
                messages.success(request, "Đã tạo tài khoản nhân viên mới thành công!")

            # 2. KHÓA / MỞ KHÓA TÀI KHOẢN
            elif action == 'toggle_lock':
                user_id = request.POST.get('user_id')
                nv = User.objects.get(id=user_id)
                nv.is_active = not nv.is_active # Đảo ngược trạng thái
                nv.save()
                tt = "MỞ KHÓA" if nv.is_active else "KHÓA"
                messages.success(request, f"Đã {tt} tài khoản {nv.username}!")

            # 3. SỬA THÔNG TIN & PHÂN QUYỀN TRẠM
            elif action == 'edit':
                user_id = request.POST.get('user_id')
                nv = User.objects.get(id=user_id)
                nv.full_name = request.POST.get('full_name')
                nv.role = request.POST.get('role')
                nv.tram_xang_id = request.POST.get('tram_id')
                
                # Nếu có nhập pass mới thì đổi pass
                new_pass = request.POST.get('password')
                if new_pass:
                    nv.set_password(new_pass)
                
                nv.save()
                messages.success(request, f"Đã cập nhật thông tin và quyền cho {nv.username}!")

            # 4. XÓA TÀI KHOẢN (Chỉ xóa nếu chưa bán hóa đơn nào)
            elif action == 'delete':
                user_id = request.POST.get('user_id')
                nv = User.objects.get(id=user_id)
                # Kiểm tra xem có dính hóa đơn không
                if HoaDon.objects.filter(nhan_vien=nv).exists():
                    messages.error(request, f"Không thể xóa {nv.username} vì người này đã có lịch sử xuất hóa đơn. Vui lòng dùng chức năng KHÓA TÀI KHOẢN thay thế!")
                else:
                    nv.delete()
                    messages.success(request, "Đã xóa vĩnh viễn tài khoản chưa phát sinh giao dịch!")

        except Exception as e:
            messages.error(request, f"Lỗi thao tác: {e}")

    return redirect('quan_ly_nhan_su')
# ==========================================
# QUẢN LÝ BẢNG GIÁ (TRONG ADMIN DASHBOARD RIÊNG)
# ==========================================
@login_required
def quan_ly_gia(request):
    if request.user.role != 'admin':
        messages.error(request, "Chỉ Giám đốc mới được điều chỉnh giá!")
        return redirect('staff_pos')

    # ĐÃ SỬA ĐÚNG CHÍNH TẢ: BangGiaNhienLieu
    from .models import BangGiaNhienLieu 

    # Tìm đoạn lấy giá từ form và thêm gia_e10 vào:
    if request.method == 'POST':
        try:
            gia_a95 = request.POST.get('gia_A95')
            gia_e5 = request.POST.get('gia_E5')
            gia_e10 = request.POST.get('gia_E10') # <--- Thêm mới
            gia_do = request.POST.get('gia_DO')

            if gia_a95: BangGiaNhienLieu.objects.update_or_create(loai_nhien_lieu='A95', defaults={'gia_ban': float(gia_a95)})
            if gia_e5: BangGiaNhienLieu.objects.update_or_create(loai_nhien_lieu='E5', defaults={'gia_ban': float(gia_e5)})
            if gia_e10: BangGiaNhienLieu.objects.update_or_create(loai_nhien_lieu='E10', defaults={'gia_ban': float(gia_e10)}) # <--- Thêm mới
            if gia_do: BangGiaNhienLieu.objects.update_or_create(loai_nhien_lieu='DO', defaults={'gia_ban': float(gia_do)})
            # ...

            messages.success(request, "Đã đồng bộ Bảng Giá mới! Toàn bộ máy POS trên hệ thống đã cập nhật.")
        except Exception as e:
            messages.error(request, f"Có lỗi xảy ra: {e}")
        
        return redirect('quan_ly_gia')

    # Lấy giá hiện tại hiển thị ra màn hình
    gia_hien_tai = {
        'A95': BangGiaNhienLieu.objects.filter(loai_nhien_lieu='A95').first(),
        'E5': BangGiaNhienLieu.objects.filter(loai_nhien_lieu='E5').first(),
        'E10': BangGiaNhienLieu.objects.filter(loai_nhien_lieu='E10').first(), # <--- Thêm mới
        'DO': BangGiaNhienLieu.objects.filter(loai_nhien_lieu='DO').first(),
    }

    return render(request, 'quan_ly_gia.html', {'gia_hien_tai': gia_hien_tai})