Parametric Tree Prediction Model


* first step:

copy the files in the FINAL_MODEL folder to the folder where your shape file is in.


* second step:

windows key + R > cmd > to open command prompt > 
run:
cd <path to the folder of the shp file> 	#not to use the <>#
than run:
python merge.py <path to shp file\shp file name1.shp> <path to shp file\shp file name2.shp> <path to shp file\output_path.shp> 	#not to use the <>#

Result will be saved in path to shp file\output_path.shp


* third step:

windows key + R > cmd > to open command prompt > 
run:
cd <path to the folder of the shp file> 	#not to use the <>#
than run:
python app.py <path to .shp file>	 	#not to use the <>#

Result will be saved as:
[path][filename]_prediction.shp



Note further onscreen info on runtime/errors.