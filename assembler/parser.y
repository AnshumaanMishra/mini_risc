%{
  #include <iostream>
  #include <string>
  #include <stdio.h>
  #include "symbol_table.hpp"
  #include "constants.hpp"

  using namespace std;
  using namespace MiniRISC;

  extern int yylex();
  extern FILE* yyin;
  void yyerror(const string& error_msg);

  uint32_t program_counter = 0;
  int pass = 1;
  SymbolTable st;
  FILE* binary_out = nullptr;
%}

%union {
  unsigned int value;
  char* label_text;
}

%token ADD SUB MUL MULU 
%token AND OR NOR XOR NOT
%token SLL SRL SRA
%token SLT SLE SGT SGE SNE SEQ

%token ADDI SUBI
%token ANDI ORI NORI XORI
%token SLLI SRLI SRAI
%token SLTI SLEI SGTI SGEI SNEI SEQI

%token LD ST
%token LI LUI
%token MOVE MFHI MFLO

%token B JAL J
%token BEQ BZ BV BLT BLE BGT BGE BNE

%token HALT NOP

%token <label_text> LABEL
%token <value> NUM REG

%type <value> STMT R I MEM MISC JUMP BRANCH
%type <value> R3 R2 R1 R2I1 R1I1 MEMRI ADDR R2A R1A

%%

PROG : PROG LINE '\n'
     | LINE '\n'
     ;
    
LINE : LABEL ':' {
         if (pass == 1) {
             st.add(string($1), program_counter);
         }
         free($1);
     }
     | STMT { 
         if (pass == 2) {
             fprintf(binary_out, "%08X\n", $1);
         }
         program_counter += 4;
     }
     | /* empty line */
     ;
    
STMT : R      { $$ = $1; }
     | I      { $$ = $1; }
     | MEM    { $$ = $1; } 
     | MISC   { $$ = $1; } 
     | JUMP   { $$ = $1; }  
     | BRANCH { $$ = $1; }
     | HALT   { $$ = OP_HALT; }
     | NOP    { $$ = OP_NOP; }
     ;

R : ADD R3  { $$ = OP_RTYPE | $2 | FN_ADD; }
  | SUB R3  { $$ = OP_RTYPE | $2 | FN_SUB; }
  | MUL R3  { $$ = OP_RTYPE | $2 | FN_MUL; }
  | MULU REG ',' REG { $$ = OP_RTYPE | (($2 & 0x1F) << 16) | (($4 & 0x1F) << 11) | FN_MULU; }
  | AND R3  { $$ = OP_RTYPE | $2 | FN_AND; }
  | OR R3   { $$ = OP_RTYPE | $2 | FN_OR; }
  | NOT R2  { $$ = OP_RTYPE | $2 | FN_NOT; }
  | NOR R3  { $$ = OP_RTYPE | $2 | FN_NOR; }
  | XOR R3  { $$ = OP_RTYPE | $2 | FN_XOR; }
  | SLL R3  { $$ = OP_RTYPE | $2 | FN_SLL; }
  | SRL R3  { $$ = OP_RTYPE | $2 | FN_SRL; }
  | SRA R3  { $$ = OP_RTYPE | $2 | FN_SRA; }
  | SLT R3  { $$ = OP_RTYPE | $2 | FN_SLT; }
  | SGT R3  { $$ = OP_RTYPE | $2 | FN_SGT; }
  | SLE R3  { $$ = OP_RTYPE | $2 | FN_SLE; }
  | SGE R3  { $$ = OP_RTYPE | $2 | FN_SGE; }
  | SEQ R3  { $$ = OP_RTYPE | $2 | FN_SEQ; }
  | SNE R3  { $$ = OP_RTYPE | $2 | FN_SNE; }
  ;
  
I : ADDI R2I1 { $$ = OP_ADDI | $2; }
  | SUBI R2I1 { $$ = OP_SUBI | $2; }
  | ANDI R2I1 { $$ = OP_ANDI | $2; }
  | ORI R2I1  { $$ = OP_ORI | $2; }
  | NORI R2I1 { $$ = OP_NORI | $2; }
  | XORI R2I1 { $$ = OP_XORI | $2; }
  | SLLI R2I1 { $$ = OP_SLLI | $2; }
  | SRLI R2I1 { $$ = OP_SRLI | $2; }
  | SRAI R2I1 { $$ = OP_SRAI | $2; }
  | SLTI R2I1 { $$ = OP_SLTI | $2; }
  | SGTI R2I1 { $$ = OP_SGTI | $2; }
  | SLEI R2I1 { $$ = OP_SLEI | $2; }
  | SGEI R2I1 { $$ = OP_SGEI | $2; }
  | SEQI R2I1 { $$ = OP_SEQI | $2; }
  | SNEI R2I1 { $$ = OP_SNEI | $2; }
  ;

MEM : LD MEMRI { $$ = OP_LD | $2; }
    | ST MEMRI { $$ = OP_ST | $2; }
    ;

MISC : LI R1I1   { $$ = OP_LI | $2; }
     | LUI R1I1  { $$ = OP_LUI | $2; }
     | MOVE R2   { $$ = OP_MOVE | $2; }
     | MFHI R1   { $$ = OP_MFHI | $2; } 
     | MFLO R1   { $$ = OP_MFLO | $2; }
     ;
    
JUMP : B ADDR { 
           uint32_t jta = ($2 / 4) & 0x3FFFFFF; 
           $$ = OP_J | jta; 
       }
     | JAL ADDR { 
           uint32_t jta = ($2 / 4) & 0x3FFFFFF; 
           $$ = OP_JAL | jta; 
       }         
     | J ADDR {
           uint32_t jta = ($2 / 4) & 0x3FFFFFF;
           $$ = OP_J | jta;
       }
     | J R1 { 
           $$ = OP_JR | (($2 >> 21) << 16);
       }
     ;

BRANCH : BEQ R2A { $$ = OP_BEQ | $2; }
       | BZ R1A  { $$ = OP_BZ  | $2; }
       | BNE R2A { $$ = OP_BNE | $2; }
       | BLT R2A { $$ = OP_BLT | $2; }
       | BLE R2A { $$ = OP_BLE | $2; }
       | BGT R2A { $$ = OP_BGT | $2; }
       | BGE R2A { $$ = OP_BGE | $2; }
       | BV R2A  { $$ = OP_BV  | $2; }
       ;


R3 : REG ',' REG ',' REG { 
         uint32_t RD = $1 & 0x1F;
         uint32_t RS = $3 & 0x1F;
         uint32_t RT = $5 & 0x1F;
         $$ = (RD << 21) | (RS << 16) | (RT << 11);
     }
   ;

R2 : REG ',' REG {
         uint32_t RD = $1 & 0x1F;
         uint32_t RS = $3 & 0x1F;
         $$ = (RD << 21) | (RS << 16);
     }
   ;

R1 : REG { 
         $$ = ($1 & 0x1F) << 21; 
     }
   ;

R2I1 : REG ',' REG ',' NUM {
           uint32_t RD = $1 & 0x1F;
           uint32_t RS = $3 & 0x1F;
           uint32_t imm = $5 & 0xFFFF;
           $$ = (RD << 21) | (RS << 16) | imm;
       }
     ;

R1I1 : REG ',' NUM {
           uint32_t RD = $1 & 0x1F;
           uint32_t imm = $3 & 0xFFFF;
           $$ = (RD << 21) | imm;
       }
     ;

MEMRI : REG ',' NUM '(' REG ')' {
            uint32_t RD = $1 & 0x1F;
            uint32_t imm = $3 & 0xFFFF;
            uint32_t RS = $5 & 0x1F;
            $$ = (RD << 21) | (RS << 16) | imm;
        }
      ;

ADDR : LABEL {
           if(st.contains(string($1))) {
               $$ = st.get(string($1));
           } else {
               if(pass == 2) {
                   string error_msg = "Undefined Label: " + string($1);
                   yyerror(error_msg);
               }
               $$ = program_counter + 4; 
           }
           free($1);
       }  
     | NUM { 
           $$ = $1; 
       }
     ;

R2A : REG ',' REG ',' ADDR {
          uint32_t RS = $1 & 0x1F;
          uint32_t RD = $3 & 0x1F;
          int32_t target_addr = $5;
          int32_t offset = (target_addr - program_counter - 4) / 4;
          
          $$ = (RD << 21) | (RS << 16) | (offset & 0xFFFF);
      }
    ;

R1A : REG ',' ADDR {
          uint32_t RS = $1 & 0x1F;
          int32_t target_addr = $3;
          int32_t offset = (target_addr - program_counter - 4) / 4;
          
          $$ = (RS << 16) | (offset & 0xFFFF);
      }
    ;

%%

void yyerror(const string& error_msg) {
    cerr << "Error at PC 0x" << hex << program_counter << ": " << error_msg << endl;
}
