
# Should be equivalent to your list of C files, if you don't build selectively
INC=inc/
SRC=$(wildcard src/*.c)
OBJ=$(SRC:.c=.o)
TARGET=libtrans.so

CFLAGS = -I$(INC) -g -lm -msse4.2 -fpic #-DVERBOSE #-DMEDIAN #-DDEBUG 
LDFLAGS= -shared

all: $(TARGET) 
	rm $(SRC:.c=.d)
	rm $(SRC:.c=.o)


$(TARGET): $(OBJ)
	gcc  $(LDFLAGS) $(CFLAGS)  -o $(TARGET) $(OBJ)

$(SRC:.c=.d):%.d:%.c
	gcc  $(CFLAGS) -MM $< >$@

include $(SRC:.c=.d)

clean:
	rm -f src/*.o 
	rm -f $(TARGET)
