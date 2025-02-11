#include <stdio.h>

int main() {

  char a = 'a';
  if (a != 'a') {
    printf("Hello\n");
  } else {
    *((volatile char*) &a) = (char)0x99;
  }
  return 0;
}
