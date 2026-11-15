"""فرم‌های فروشگاه آب پاک"""
from django import forms
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import PROVINCES, ContactMessage, Profile
from .utils import digits_only, is_valid_mobile, normalize_digits

User = get_user_model()


class StyledFormMixin:
    """کلاس‌های مشترک برای ورودی‌های فرم"""

    def _style_fields(self):
        for name, field in self.fields.items():
            widget = field.widget
            css = "field__input"
            if isinstance(widget, forms.Select):
                css = "field__input field__input--select"
            elif isinstance(widget, forms.Textarea):
                css = "field__input field__input--textarea"
            elif isinstance(widget, forms.CheckboxInput):
                css = "field__checkbox"
            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{existing} {css}".strip()
            if not isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("placeholder", field.label or "")
            if field.required:
                widget.attrs["required"] = True


class CheckoutForm(StyledFormMixin, forms.Form):
    full_name = forms.CharField(
        label="نام و نام خانوادگی", max_length=150, min_length=3, strip=True,
        error_messages={"required": "نام و نام خانوادگی را وارد کنید.", "min_length": "نام وارد شده کوتاه است."},
    )
    phone = forms.CharField(label="شماره تماس", max_length=15)
    province = forms.ChoiceField(label="استان", choices=PROVINCES)
    city = forms.CharField(label="شهر", max_length=80)
    address = forms.CharField(
        label="آدرس کامل پستی", max_length=500, widget=forms.Textarea(attrs={"rows": 3}),
        error_messages={"required": "آدرس تحویل سفارش را وارد کنید."},
    )
    postal_code = forms.CharField(label="کد پستی", max_length=15)
    note = forms.CharField(
        label="توضیحات سفارش (اختیاری)", max_length=600, required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "مثلاً: ساعت تحویل، جزئیات نصب…"}),
    )
    shipping_method = forms.ChoiceField(
        label="روش ارسال",
        choices=[(key, value["label"]) for key, value in settings.SHIPPING_METHODS.items()],
        initial=settings.DEFAULT_SHIPPING_METHOD,
        widget=forms.RadioSelect,
    )
    payment_method = forms.ChoiceField(
        label="روش پرداخت",
        choices=[(key, value["label"]) for key, value in settings.PAYMENT_METHODS.items()],
        initial="cod",
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self._style_fields()
        if user is not None and user.is_authenticated:
            profile = getattr(user, "profile", None)
            self.fields["full_name"].initial = user.get_full_name() or user.first_name
            if profile:
                self.fields["phone"].initial = profile.phone
                self.fields["province"].initial = profile.province
                self.fields["city"].initial = profile.city
                self.fields["address"].initial = profile.address
                self.fields["postal_code"].initial = profile.postal_code
            if user.email:
                pass

    def clean_full_name(self):
        value = self.cleaned_data["full_name"].strip()
        if len(value.split()) < 2:
            raise ValidationError("نام و نام خانوادگی را کامل وارد کنید.")
        return value

    def clean_phone(self):
        value = digits_only(self.cleaned_data["phone"])
        if not is_valid_mobile(value):
            raise ValidationError("شماره تماس باید ۱۱ رقم و با ۰۹ شروع شود.")
        return value

    def clean_postal_code(self):
        value = digits_only(self.cleaned_data["postal_code"])
        if len(value) != 10:
            raise ValidationError("کد پستی باید ۱۰ رقم باشد.")
        return value

    def clean_address(self):
        value = self.cleaned_data["address"].strip()
        if len(value) < 10:
            raise ValidationError("آدرس را کامل‌تر وارد کنید (حداقل ۱۰ کاراکتر).")
        return value


class ContactForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["full_name", "phone", "email", "subject", "message"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()
        self.fields["email"].required = False
        self.fields["message"].widget.attrs["rows"] = 4
        self.fields["phone"].widget.attrs["placeholder"] = "۰۹۱۲۳۴۵۶۷۸۹"

    def clean_phone(self):
        value = digits_only(self.cleaned_data["phone"])
        if not is_valid_mobile(value):
            raise ValidationError("شماره تماس باید ۱۱ رقم و با ۰۹ شروع شود.")
        return value

    def clean_message(self):
        value = self.cleaned_data["message"].strip()
        if len(value) < 10:
            raise ValidationError("متن پیام حداقل ۱۰ کاراکتر باشد.")
        return value


class RegisterForm(StyledFormMixin, forms.Form):
    full_name = forms.CharField(label="نام و نام خانوادگی", max_length=150)
    phone = forms.CharField(label="شماره تماس", max_length=15)
    email = forms.EmailField(label="ایمیل (اختیاری)", required=False)
    password1 = forms.CharField(label="رمز عبور", min_length=8, widget=forms.PasswordInput)
    password2 = forms.CharField(label="تکرار رمز عبور", min_length=8, widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()
        self.fields["password1"].widget.attrs["placeholder"] = "حداقل ۸ کاراکتر"
        self.fields["password2"].widget.attrs["placeholder"] = "رمز عبور را دوباره وارد کنید"

    def clean_full_name(self):
        value = self.cleaned_data["full_name"].strip()
        if len(value.split()) < 2:
            raise ValidationError("نام و نام خانوادگی را کامل وارد کنید.")
        return value

    def clean_phone(self):
        value = digits_only(self.cleaned_data["phone"])
        if not is_valid_mobile(value):
            raise ValidationError("شماره تماس باید ۱۱ رقم و با ۰۹ شروع شود.")
        if User.objects.filter(username=value).exists():
            raise ValidationError("این شماره قبلاً ثبت‌نام کرده است. وارد شوید.")
        return value

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "رمز عبور و تکرار آن یکسان نیستند.")
        if password1:
            try:
                validate_password(password1)
            except ValidationError as error:
                self.add_error("password1", error)
        return cleaned

    def save(self):
        data = self.cleaned_data
        parts = data["full_name"].split()
        first_name, last_name = parts[0], " ".join(parts[1:])
        user = User.objects.create_user(
            username=data["phone"],
            email=data["email"] or "",
            password=data["password1"],
            first_name=first_name,
            last_name=last_name,
        )
        Profile.objects.update_or_create(user=user, defaults={"phone": data["phone"]})
        return user


class LoginForm(StyledFormMixin, forms.Form):
    phone = forms.CharField(label="شماره تماس", max_length=15)
    password = forms.CharField(label="رمز عبور", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        self._style_fields()
        self.fields["phone"].widget.attrs["placeholder"] = "۰۹۱۲۳۴۵۶۷۸۹"
        self.fields["password"].widget.attrs["placeholder"] = "رمز عبور خود را وارد کنید"
        self.fields["phone"].widget.attrs["autofocus"] = True
        self.user = None

    def clean(self):
        cleaned = super().clean()
        phone = digits_only(cleaned.get("phone", ""))
        password = cleaned.get("password")
        if phone and password:
            if not is_valid_mobile(phone):
                raise ValidationError("شماره تماس معتبر نیست.")
            self.user = authenticate(self.request, username=phone, password=password)
            if self.user is None:
                raise ValidationError("شماره تماس یا رمز عبور اشتباه است.")
            if not self.user.is_active:
                raise ValidationError("حساب کاربری شما غیرفعال است.")
        return cleaned


class ProfileForm(StyledFormMixin, forms.ModelForm):
    full_name = forms.CharField(label="نام و نام خانوادگی", max_length=150)
    email = forms.EmailField(label="ایمیل", required=False)

    class Meta:
        model = Profile
        fields = ["phone", "province", "city", "address", "postal_code"]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self._style_fields()
        self.fields["full_name"].initial = self.user.get_full_name()
        self.fields["email"].initial = self.user.email
        self.fields["province"].choices = [("", "انتخاب استان")] + PROVINCES
        self.fields["postal_code"].widget.attrs["placeholder"] = "۱۰ رقم"

    def clean_phone(self):
        value = normalize_digits(self.cleaned_data.get("phone", ""))
        if value and not is_valid_mobile(value):
            raise ValidationError("شماره تماس باید ۱۱ رقم و با ۰۹ شروع شود.")
        return value

    def save(self, commit=True):
        profile = super().save(commit=False)
        parts = self.cleaned_data["full_name"].split()
        self.user.first_name = parts[0] if parts else ""
        self.user.last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        self.user.email = self.cleaned_data.get("email", "")
        self.user.save()
        if commit:
            profile.save()
        return profile


class OrderTrackForm(StyledFormMixin, forms.Form):
    code = forms.CharField(label="کد سفارش", max_length=30)
    phone = forms.CharField(label="شماره تماس ثبت سفارش", max_length=15)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()
        self.fields["code"].widget.attrs["placeholder"] = "مثال: ABP-241105-A1B2C"
        self.fields["phone"].widget.attrs["placeholder"] = "۰۹۱۲۳۴۵۶۷۸۹"

    def clean_code(self):
        return normalize_digits(self.cleaned_data["code"]).strip().upper()

    def clean_phone(self):
        value = digits_only(self.cleaned_data["phone"])
        if not is_valid_mobile(value):
            raise ValidationError("شماره تماس معتبر نیست.")
        return value
