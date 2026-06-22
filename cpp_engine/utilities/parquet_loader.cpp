#include "parquet_loader.hpp"
#include <algorithm>
#include <array>
#include <arrow/api.h>
#include <arrow/io/api.h>
#include <chrono>
#include <filesystem>
#include <iterator>
#include <parquet/arrow/reader.h>
#include <ranges>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace backtest {

namespace {

using namespace arrow;
using namespace parquet::arrow;

auto TsToIso(Timestamp ts) -> std::string {
    auto t = std::chrono::system_clock::to_time_t(ts);
    std::tm* tm = std::gmtime(&t);
    if (tm == nullptr) {
        return "";
    }
    std::array<char, 32> buf{};
    std::snprintf(buf.data(), buf.size(), "%04d-%02d-%02dT%02d:%02d:%02dZ", tm->tm_year + 1900,
                  tm->tm_mon + 1, tm->tm_mday, tm->tm_hour, tm->tm_min, tm->tm_sec);
    return buf.data();
}

} // namespace

bool ArrowParquetLoader::load(std::string const& path, std::string const& time_column) {
    meta_.path = path;
    meta_.time_column = time_column;
    table_.reset();
    time_col_index_ = -1;

    std::string resolved = path;
    if (!std::filesystem::path(path).is_absolute()) {
        std::filesystem::path cwd = std::filesystem::current_path();
        if (cwd.filename() == "build") {
            cwd = cwd.parent_path();
        }
        resolved = (cwd / path).string();
    }

    // Memory-mapped open (efficient)
    std::shared_ptr<io::MemoryMappedFile> infile;
    auto status = io::MemoryMappedFile::Open(resolved, io::FileMode::READ);
    if (!status.ok()) {
        return false;
    }
    infile = *status;

    // Parquet reader
    std::unique_ptr<FileReader> reader;
    auto open_status = OpenFile(infile, default_memory_pool(), &reader);
    if (!open_status.ok()) {
        return false;
    }

    // Read table
    std::shared_ptr<Table> table;
    PARQUET_THROW_NOT_OK(reader->ReadTable(&table));
    if (!table) {
        return false;
    }
    table_ = table;

    meta_.row_count = table_->num_rows();
    auto* schema = table_->schema().get();
    time_col_index_ = schema->GetFieldIndex(time_column);
    if (time_col_index_ < 0) {
        return false;
    }

    if (meta_.row_count > 0) {
        const Array* ts_arr = detail::ColumnChunk0(table_.get(), time_col_index_);
        if (ts_arr != nullptr) {
            if (ts_arr->type_id() == Type::TIMESTAMP) {
                const auto* ts = static_cast<const TimestampArray*>(ts_arr);
                auto ts_type = std::static_pointer_cast<TimestampType>(ts_arr->type());
                auto unit = ts_type->unit();
                meta_.ts_start = TsToIso(detail::ArrowTsToChrono(ts->Value(0), unit));
                meta_.ts_end = TsToIso(detail::ArrowTsToChrono(ts->Value(ts->length() - 1), unit));
            } else if (ts_arr->type_id() == Type::INT64) {
                const auto* ts = static_cast<const Int64Array*>(ts_arr);
                meta_.ts_start = TsToIso(detail::ArrowInt64ToChrono(ts->Value(0)));
                meta_.ts_end = TsToIso(detail::ArrowInt64ToChrono(ts->Value(ts->length() - 1)));
            }
        }
    }
    return true;
}

auto ArrowParquetLoader::get_meta() const -> DataMeta { return meta_; }

void ArrowParquetLoader::collect_symbols(std::unordered_set<std::string>& out) const {
    if (!table_) {
        return;
    }
    const int col_sym = table_->schema()->GetFieldIndex("symbol");
    if (col_sym < 0) {
        return;
    }
    const Array* arr = detail::ColumnChunk0(table_.get(), col_sym);
    if (arr == nullptr) {
        return;
    }
    const bool is_string = (arr->type_id() == Type::STRING);
    const bool is_large_string = (arr->type_id() == Type::LARGE_STRING);
    if (!is_string && !is_large_string) {
        return;
    }
    if (arr->null_count() == arr->length()) {
        return;
    }
    const int64_t n = arr->length();
    for (int64_t i = 0; i < n; ++i) {
        if (arr->IsNull(i)) {
            continue;
        }
        std::string s;
        if (is_string) {
            s = static_cast<const StringArray*>(arr)->GetString(i);
        } else {
            s = static_cast<const LargeStringArray*>(arr)->GetString(i);
        }
        if (!s.empty()) {
            out.insert(std::move(s));
        }
    }
}

auto make_parquet_loader() -> std::unique_ptr<ArrowParquetLoader> {
    return std::make_unique<ArrowParquetLoader>();
}

} // namespace backtest
