include ../include/generated/variables.mak
include $(SOC_DIRECTORY)/software/common.mak

OBJECTS = sdram.o bist.o sdram_dbg.o sdram_spd.o utils.o accessors.o sdram_rcd.o
OBJECTS += utils/eye_detection_helper.o
OBJECTS += ddr5/ddr5_spd_parse.o ddr5_training.o ddr5_helpers.o
OBJECTS += lpddr5_training.o lpddr5_helpers.o


all: liblitedram.a

liblitedram.a: $(OBJECTS)
	$(AR) crs liblitedram.a $(OBJECTS)

# pull in dependency info for *existing* .o files
-include $(OBJECTS:.o=.d)

ddr5/%.o: $(LIBLITEDRAM_DIRECTORY)/ddr5/%.c
	mkdir -p ddr5
	$(compile)

utils/%.o: $(LIBLITEDRAM_DIRECTORY)/utils/%.c
	mkdir -p utils
	$(compile)

%.o: $(LIBLITEDRAM_DIRECTORY)/%.c
	$(compile)

%.o: %.S
	$(assemble)

.PHONY: all clean

clean:
	$(RM) $(OBJECTS) liblitedram.a .*~ *~
