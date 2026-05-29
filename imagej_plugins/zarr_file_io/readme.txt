Compiling and using the .zarr reader plugins with Fiji/ImageJ

Folder layout
-------------

This folder has two separate plugin components:

zarr_reader/
    Zarr_Reader.java
    plugins.config

zarr_drag_and_drop/
    Zarr_Drag_And_Drop.java
    plugins.config
    Install_Zarr_Drag_And_Drop.js

Each component has its own plugins.config file. This means there is no need to
copy or rename drag_plugins.config during packaging.


What each component does
------------------------

Zarr_Reader.jar opens Zarr files from the Fiji menu:

    File > Open > Zarr...
    Plugins > Zarr Reader

Zarr_Drag_And_Drop.jar fixes drag/drop of .zarr folders. Fiji normally treats
dropped folders as image sequences before HandleExtraFileTypes sees them. This
helper intercepts only Zarr-looking folders and sends them to Zarr_Reader. All
other files and folders use Fiji's normal drag/drop behavior.

Install_Zarr_Drag_And_Drop.js is an AutoRun script. It installs the custom
drag/drop handler every time Fiji starts.


Installing on another Fiji
--------------------------

Copy these files:

built_jars/Zarr_Reader.jar -> Fiji.app/plugins/Zarr_Reader.jar
built_jars/Zarr_Drag_And_Drop.jar -> Fiji.app/plugins/Zarr_Drag_And_Drop.jar
zarr_drag_and_drop/Install_Zarr_Drag_And_Drop.js -> Fiji.app/scripts/Plugins/AutoRun/Install_Zarr_Drag_And_Drop.js

Then restart Fiji.


Compile from source
-------------------

Run these commands from the top-level zarr_plugin folder, not from this
zarr_file_io folder.

If using Java 9 or newer javac, compile Java 8-compatible class files with:

javac --release 8 -cp "Fiji.app/jars/*;Fiji.app/plugins/*" imagej_plugins/zarr_file_io/zarr_reader/Zarr_Reader.java imagej_plugins/zarr_file_io/zarr_drag_and_drop/Zarr_Drag_And_Drop.java

If using Java 8 javac, use:

javac -source 1.8 -target 1.8 -cp "Fiji.app/jars/*;Fiji.app/plugins/*" imagej_plugins/zarr_file_io/zarr_reader/Zarr_Reader.java imagej_plugins/zarr_file_io/zarr_drag_and_drop/Zarr_Drag_And_Drop.java

The javac command creates .class files only:

zarr_reader/Zarr_Reader.class
zarr_drag_and_drop/Zarr_Drag_And_Drop.class


Package the jars
----------------

Run these commands from the top-level zarr_plugin folder.

Make Zarr_Reader.jar:

jar cf imagej_plugins/zarr_file_io/built_jars/Zarr_Reader.jar -C imagej_plugins/zarr_file_io/zarr_reader Zarr_Reader.class -C imagej_plugins/zarr_file_io/zarr_reader Zarr_Reader.java -C imagej_plugins/zarr_file_io/zarr_reader plugins.config

Make Zarr_Drag_And_Drop.jar:

jar cf imagej_plugins/zarr_file_io/built_jars/Zarr_Drag_And_Drop.jar -C imagej_plugins/zarr_file_io/zarr_drag_and_drop Zarr_Drag_And_Drop.class -C imagej_plugins/zarr_file_io/zarr_drag_and_drop Zarr_Drag_And_Drop.java -C imagej_plugins/zarr_file_io/zarr_drag_and_drop plugins.config

Copy the AutoRun script into Fiji:

copy imagej_plugins\zarr_file_io\zarr_drag_and_drop\Install_Zarr_Drag_And_Drop.js Fiji.app\scripts\Plugins\AutoRun\Install_Zarr_Drag_And_Drop.js

Restart Fiji after compiling, packaging, or copying these files.


Notes
-----

Forward slashes or backslashes both usually work in javac and jar paths on
Windows. Keep the semicolon in the classpath on Windows:

    -cp "Fiji.app/jars/*;Fiji.app/plugins/*"

On macOS/Linux, the classpath separator is a colon instead:

    -cp "Fiji.app/jars/*:Fiji.app/plugins/*"

The reader supports the storm-control Zarr writer layout:

    <movie>.zarr/data

with uint16 data, shape=(frames, y, x), chunks=(1, y, x), and Blosc lz4
bitshuffle compression.

The reader searches recursively for the first Zarr dataset, so the dataset does
not have to be named "data". If a Zarr group contains multiple datasets, this
simple reader opens the first one it finds.

The current native Blosc path setup is Windows-specific:

    Fiji.app/lib/win64/blosc.dll

For macOS or Linux, Zarr_Reader.java would need a small update to look for the
native Blosc library in the appropriate Fiji lib folder.
