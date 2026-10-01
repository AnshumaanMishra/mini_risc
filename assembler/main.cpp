#include "parser.tab.hpp"
#include <cstdint>
#include <iostream>
#include <stdio.h>

extern FILE *yyin;
extern int yyparse();
extern void yyrestart(FILE *);

extern int pass;
extern uint32_t program_counter;
extern FILE *binary_out;

int main(int argc, char **argv) {
  if (argc < 3) {
    std::cerr << "Usage: " << argv[0] << " <input.s> <output.bin>\n";
    return 1;
  }

  FILE *input_file = fopen(argv[1], "r");
  if (!input_file) {
    std::cerr << "Failed to open input file: " << argv[1] << "\n";
    return 1;
  }

  pass = 1;
  program_counter = 0;
  yyin = input_file;
  std::cout << "Starting Pass 1 (Address Resolution)..." << std::endl;
  yyparse();

  fseek(input_file, 0, SEEK_SET);
  yyrestart(input_file);

  binary_out = fopen(argv[2], "w");
  if (!binary_out) {
    std::cerr << "Failed to create output file: " << argv[2] << "\n";
    fclose(input_file);
    return 1;
  }

  pass = 2;
  program_counter = 0;
  std::cout << "Starting Pass 2 (Code Emission)..." << std::endl;
  yyparse();

  std::cout << "Assembly successful. Binary written to: " << argv[2]
            << std::endl;

  fclose(input_file);
  fclose(binary_out);
  return 0;
}
