%{
#include "parser.tab.hpp"
#include <string.h>
#include <stdlib.h>
%}

%option noyywrap
%option case-insensitive

%%

"add"     { return ADD; }
"sub"     { return SUB; }
"mul"     { return MUL; }
"mulu"    { return MULU; }
"and"     { return AND; }
"or"      { return OR; }
"nor"     { return NOR; }
"xor"     { return XOR; }
"not"     { return NOT; }
"sll"     { return SLL; }
"srl"     { return SRL; }
"sra"     { return SRA; }
"slt"     { return SLT; }
"sle"     { return SLE; }
"sgt"     { return SGT; }
"sge"     { return SGE; }
"sne"     { return SNE; }
"seq"     { return SEQ; }

"addi"    { return ADDI; }
"subi"    { return SUBI; }
"andi"    { return ANDI; }
"ori"     { return ORI; }
"nori"    { return NORI; }
"xori"    { return XORI; }
"slli"    { return SLLI; }
"srli"    { return SRLI; }
"srai"    { return SRAI; }
"slti"    { return SLTI; }
"slei"    { return SLEI; }
"sgti"    { return SGTI; }
"sgei"    { return SGEI; }
"snei"    { return SNEI; }
"seqi"    { return SEQI; }

"ld"      { return LD; }
"st"      { return ST; }
"li"      { return LI; }
"lui"     { return LUI; }
"move"    { return MOVE; }
"mfhi"    { return MFHI; }
"mflo"    { return MFLO; }

"b"       { return B; }
"jal"     { return JAL; }
"j"       { return J; }
"beq"     { return BEQ; }
"bz"      { return BZ; }
"bv"      { return BV; }
"blt"     { return BLT; }
"ble"     { return BLE; }
"bgt"     { return BGT; }
"bge"     { return BGE; }
"bne"     { return BNE; }

"halt"    { return HALT; }
"nop"     { return NOP; }

\$[0-9]+  { 
    yylval.value = atoi(yytext + 1); 
    return REG; 
}

[-]?[0-9]+ { 
    yylval.value = atoi(yytext); 
    return NUM; 
}

0x[0-9a-fA-F]+ {
    yylval.value = strtol(yytext, NULL, 16);
    return NUM;
}

[a-zA-Z_][a-zA-Z0-9_]* { 
    yylval.label_text = strdup(yytext); 
    return LABEL; 
}

[ \t\r]+  { /* Ignore whitespace */ }

\n        { return '\n'; }
","       { return ','; }
":"       { return ':'; }
"("       { return '('; }
")"       { return ')'; }

.         { /* Ignore unrecognized characters or handle errors here */ }

%%
