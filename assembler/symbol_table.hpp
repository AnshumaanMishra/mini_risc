#pragma once
#ifndef SYMBOLTABLE_HPP
#define SYMBOLTABLE_HPP

#include <cstdint>
#include <string>
#include <unordered_map>

class SymbolTable {
private:
  std::unordered_map<std::string, uint32_t> table;

public:
  void add(const std::string &label, uint32_t address);
  bool contains(const std::string &label) const;
  uint32_t get(const std::string &label) const;
};

#endif
