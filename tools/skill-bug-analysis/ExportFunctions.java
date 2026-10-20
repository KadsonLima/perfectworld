import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

import java.io.File;
import java.io.PrintWriter;

public class ExportFunctions extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException("usage: <output-file> <hex-address>...");
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("could not open program in decompiler");
        }

        try (PrintWriter out = new PrintWriter(new File(args[0]), "UTF-8")) {
            out.println("PROGRAM " + currentProgram.getName());
            for (int i = 1; i < args.length; i++) {
                long value = Long.parseUnsignedLong(args[i].replaceFirst("^(0x|0X)", ""), 16);
                Address address = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
                Function function = getFunctionAt(address);
                out.println();
                out.println("ADDRESS " + address);
                if (function == null) {
                    out.println("FUNCTION_NOT_FOUND");
                    continue;
                }
                out.println("FUNCTION " + function.getName(true));
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                if (result.decompileCompleted()) {
                    out.println(result.getDecompiledFunction().getC());
                } else {
                    out.println("DECOMPILE_FAILED " + result.getErrorMessage());
                }
                out.flush();
            }
        } finally {
            decompiler.dispose();
        }
    }
}
