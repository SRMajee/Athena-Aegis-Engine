#include <cstring>
#include <cstdlib>
#include <cstdio>

typedef unsigned long long Decimal;

extern "C" {

Decimal __binary64_to_bid64(double d, unsigned int, unsigned int*) {
    if (d == 1.7976931348623157e+308) {
        return 18446744073709551615ULL; // ULLONG_MAX
    }
    Decimal out = 0;
    std::memcpy(&out, &d, sizeof(double));
    return out;
}

double __bid64_to_binary64(Decimal dec, unsigned int, unsigned int*) {
    if (dec == 18446744073709551615ULL) {
        return 1.7976931348623157e+308;
    }
    double out = 0.0;
    std::memcpy(&out, &dec, sizeof(double));
    return out;
}

Decimal __bid64_from_string(char* s, unsigned int, unsigned int*) {
    if (!s || !*s) {
        return 18446744073709551615ULL;
    }
    double d = std::strtod(s, nullptr);
    return __binary64_to_bid64(d, 0, nullptr);
}

void __bid64_to_string(char* buf, Decimal dec, unsigned int*) {
    if (dec == 18446744073709551615ULL) {
        std::strcpy(buf, "");
        return;
    }
    double d = __bid64_to_binary64(dec, 0, nullptr);
    std::sprintf(buf, "%f", d);
    char* dot = std::strchr(buf, '.');
    if (dot != nullptr) {
        char* p = buf + std::strlen(buf) - 1;
        while (p > dot && *p == '0') {
            *p = '\0';
            p--;
        }
        if (p == dot) {
            *p = '\0';
        }
    }
}

Decimal __bid64_add(Decimal a, Decimal b, unsigned int, unsigned int*) {
    double da = __bid64_to_binary64(a, 0, nullptr);
    double db = __bid64_to_binary64(b, 0, nullptr);
    return __binary64_to_bid64(da + db, 0, nullptr);
}

Decimal __bid64_sub(Decimal a, Decimal b, unsigned int, unsigned int*) {
    double da = __bid64_to_binary64(a, 0, nullptr);
    double db = __bid64_to_binary64(b, 0, nullptr);
    return __binary64_to_bid64(da - db, 0, nullptr);
}

Decimal __bid64_mul(Decimal a, Decimal b, unsigned int, unsigned int*) {
    double da = __bid64_to_binary64(a, 0, nullptr);
    double db = __bid64_to_binary64(b, 0, nullptr);
    return __binary64_to_bid64(da * db, 0, nullptr);
}

Decimal __bid64_div(Decimal a, Decimal b, unsigned int, unsigned int*) {
    double da = __bid64_to_binary64(a, 0, nullptr);
    double db = __bid64_to_binary64(b, 0, nullptr);
    return __binary64_to_bid64(da / db, 0, nullptr);
}

} // extern "C"
