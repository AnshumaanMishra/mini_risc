#include "symbol_table.hpp"

void SymbolTable::add(const std::string &label, uint32_t address) {
  table[label] = address;
}

bool SymbolTable::contains(const std::string &label) const {
  return table.find(label) != table.end();
}

uint32_t SymbolTable::get(const std::string &label) const {
  auto it = table.find(label);
  if (it != table.end()) {
    return it->second;
  }
  return 0;
}
