# Sorting and Searching
sorting\_and\_searching\.pptx

######\# 871BFD9129DB47B2BB01AEDCAF994603

---

## List


### import  java\.util\.List;

| frequently used methods |  |
| --- | --- |
| Name | Use |
| indexOf(x) | returns -1 if not foundreturns loc in list if found |
| contains(x) | returns true if x exists in listreturns false if x does not exist in list |
| equals(x) | returns true if this list is equal to x |

### Speaker notes
The List interface which is implemented by the ArrayList class has many useful methods\.
indexOf\(\) and contains\(\)  will search a list for a specified item\.
equals\(\) will see if two lists contain the exact same items in the exact same order\.

---

## 🛝
SNIPPET

- ArrayList `<Integer>` ray;
- ray=new ArrayList `<Integer>` \(\);
- ray\.add\(21\);
- ray\.add\(14\);
- ray\.add\(0,13\);
- ray\.add\(25\);
- out\.println\( ray\.indexOf\( 21 \) \);
- out\.println\( ray\.indexOf\( 17 \) \);
- out\.println\( ray\.contains\(25 \) \);
- out\.println\( ray\.contains\( 63 \) \);
OUTPUT
- 1
- \-1
- true
- false

### Speaker notes
sort\(\) will naturally order the items in the Collection\.

---

## Arrays


### import  java\.util\.Arrays;

| frequently used methods |  |
| --- | --- |
| Name | Use |
| sort(x) | puts all items in x in ascending order |
| binarySearch(x,y) | checks x for the location of y |
| equals(x,y) | checks if x and y have the same values |
| fill(x, y) | fills all spots in x with value y |

### Speaker notes
The Arrays class methods above are very useful methods for manipulating Java arrays\.
sort\(\) will naturally order the items in an array\.
binarySearch\(\)  will find an item in the array and return the spot at which the item was found\.
equals\(\) will see if two arrays contain the exact same items in the exact same order\.
fill\(\) will fill in all spots in the array with a provided value\.

---

## Java Searches
SNIPPET

```
String s  = "abcdefghijklmnop";
```



```
out\\\.println\\\(s\\\.indexOf\\\("3"\\\)\\\);
```



```
int\\\[\\\] ray = \\\{3,4,5,6,11,18,91\\\};
```



```
out\\\.println\\\(Arrays\\\.binarySearch\\\(ray,5\\\)\\\);
```



```
int\\\[\\\] ray = \\\{3,4,5,6,11,18,91\\\};
```



```
out\\\.println\\\(Arrays\\\.binarySearch\\\(ray,15\\\)\\\);
```



OUTPUT

- `\\\-1` 
- `2` 
- `\\\-6` 

### Speaker notes
indexOf\(\) and binarySearch\(\) seach and array for specified value\.
indexOf\(\) will return the spot at which the item was found\.   It will return \-1 if the item was not present\.
binarySearch\(\) will return the spot at which the item was found\.   It will return \-1 \+ \-location\(where the item should be\) if the item was not present\.

---

## Java Sorts
SNIPPET

```
int\\\[\\\] ray = \\\{13,6,17,18,2,\\\-5\\\};
```



```
Arrays\\\.sort\\\(ray\\\);
```



```
for\\\(int i = 0; i < ray\\\.length; i\\\+\\\+\\\)
```



```
\\\{
```



```
out\\\.println\\\(ray\\\[i\\\]\\\);
```



```
\\\}
```



OUTPUT

- `\\\-5` 
- `2` 
- `6` 
- `13` 
- `17` 
- `18` 

### Speaker notes
sort\(\) will naturally order the items in an array\.

---

## Collections


### import  java\.util\.Collections;

| frequently used methods |  |
| --- | --- |
| Name | Use |
| sort(x) | puts all items in x in ascending order |
| binarySearch(x,y) | checks x for the location of y |
| fill(x,y) | fills all spots in x with value y |
| rotate(x) | shifts items in x left or right |
| reverse(x) | reverses the order of all items in x |

### Speaker notes
The Collections class methods above are very useful methods for manipulating Java Collections\.
sort\(\) will naturally order the items in the collection\.
binarySearch\(\)  will find an item in the array and return the spot at which the item was found\.
fill\(\) will fill in all spots in the array with a provided value\.
rotate\(\) will shift items to the left\(\- negative x\) a specified amount or shift items to the right\(\+ positive x\) a specified amount\.
reverse\(\) will reverse the order of all items\.

---

## Java Sorts
SNIPPET

- ArrayList `<Integer>` ray;
- ray=new ArrayList `<Integer>` \(\);
- ray\.add\(21\);
- ray\.add\(2\);
- ray\.add\(13\);
- ray\.add\(\-1\);
- ray\.add\(3\);
- Collections\.sort\(ray\);
- for\(int  num  :  ray \)
- out\.println\(num\);
OUTPUT
- 1231321

### Speaker notes
sort\(\) will naturally order the items in the Collection\.

---

## Linear with Primitives

```
int linearSearch\\\(int\\\[\\\] stuff, int val\\\)
```



```
\\\{
```



```
for\\\(int i=0; i< stuff\\\.length; i\\\+\\\+\\\)
```



```
\\\{
```



```
if \\\(stuff\\\[i\\\] == val \\\)
```



```
return i;
```



```
\\\}
```



```
return \\\-1;   //returns \\\-1 if not found
```



```
\\\}
```



- The Linear Search searches sequentially through a list one element at time looking for a match\.
- The index position of a match is returned if found or \-1 is returned if no match is found\.

---

## Linear with Objects

```
int linearSearch\\\(Comparable\\\[\\\] stuff,
```



```
Comparable item\\\)
```



```
\\\{
```



```
for\\\(int i=0; i<stuff\\\.length; i\\\+\\\+\\\)
```



```
\\\{
```



```
if \\\(stuff\\\[i\\\]\\\.compareTo\\\(item\\\)==0\\\)
```



```
return i;
```



```
\\\}
```



```
return \\\-1;   //returns \\\-1 if not found
```



```
\\\}
```


---

## 🛝
- 1/2
- Binary Search
- 0100100101

---

## BinarySearch
- The Binary Search works best with sorted lists\.  The Binary search cuts the list in half each time it checks for for the specified value\.  If the value is not found, the search continue in the half most likely to contain the value\.

```
int binarySearch \\\(int \\\[\\\] stuff, int val \\\)
```



```
\\\{
```



```
int bot= 0, top = stuff\\\.length\\\-1;
```



```
while\\\(bot<=top\\\)
```



```
\\\{
```



```
int middle = \\\(bot \\\+ top\\\) / 2;
```



```
if \\\(stuff\\\[middle\\\] == val\\\)  return middle;
```



```
else
```



```
if \\\(stuff\\\[middle\\\] > val\\\)
```



```
top = middle\\\-1;
```



```
else
```



```
bot = middle\\\+1;
```



```
\\\}
```



```
return \\\-1;
```



```
\\\}
```


---

## BinarySearch

```
public static int binarySearch \\\(int \\\[\\\] s, int v,
```



```
int b, int t \\\)
```



```
\\\{
```



```
if\\\(b<=t\\\)
```



```
\\\{
```



```
int m = \\\(b \\\+ t\\\) / 2;
```



```
if \\\(s\\\[m\\\] == v\\\)
```



```
return m;
```



```
if \\\(s\\\[m\\\] > v\\\)
```



```
return binarySearch\\\(s, v, b, m\\\-1\\\);
```



```
return binarySearch\\\(s, v, m\\\+1, t\\\);
```



```
\\\}
```



```
return \\\-1;
```



```
\\\}
```


---

## BinarySearch


### If you are searching for 25, how many times will you check the stuff?

```
int\\\[\\\] stuff = \\\{1,6,8,10,14,22,30,50\\\};
```



```
0 \\\+ 7 = 7 / 2 = 3
```



```
stuff\\\[3\\\] = 10
```



```
4 \\\+ 7 = 11 div 2 = 5
```



```
stuff\\\[5\\\] = 22
```



```
6 \\\+ 7 = 13 div 2 = 6
```



```
stuff\\\[6\\\] = 30
```


---

## Binary Search ShortCut
- Given a list of N items\.
- What is the next largest power of 2?
- If N is 100, the next largest power of 2 is 7\.
- Log2\(100\) = 6\.64386
- 27 = 128\.
- It would take 7 checks max to find if an item existed in a list of 100 items\.

---

## General Big O Chart
- for Searches
- Name          Best Case   Avg\. Case   Worst Case
- Linear/Sequential Search     O\(1\)         O\(N\)        O\(N\)
- Binary Search        O\(1\)     O\( log2 N \) O\( log2 N \)
- All searches have a best case run time of O\(1\) if written properly\.
- You have to look at the code to determine if the search has the
- ability to find the item and return immediately\.  If this case is present,
- the algorithm can have a best case of O\(1\)\.

---

## Selection Sort
- The selection sort does not swap each time it finds elements out of position\.
- Selection sort makes a complete pass while searching for the next item to swap\.  At the end of a pass once the item is located, one swap is made\.

```
void selectionSort\\\( int\\\[\\\] ray  \\\)
```



```
\\\{
```



```
for\\\(int i=0; i< ray\\\.length\\\-1; i\\\+\\\+\\\)
```



```
\\\{
```



```
int min = i;
```



```
for\\\(int j = i\\\+1; j< ray\\\.length; j\\\+\\\+\\\)
```



```
\\\{
```



```
if\\\(ray\\\[j\\\] < ray\\\[min\\\]\\\)
```



```
min = j;  //find location of smallest
```



```
\\\}
```



```
if\\\( min \\\!= i\\\) \\\{
```



```
int temp = ray\\\[min\\\];
```



```
ray\\\[min\\\] = ray\\\[i\\\];
```



```
ray\\\[i\\\] = temp;    //put smallest in pos i
```



```
\\\}
```



```
\\\}
```



```
\\\}
```



### Speaker notes
Selection sort is pretty effective for small lists, but pretty horrible is used on large lists\.
Selection sort consists of two loops\.
The outer loops run based on the number of items in the list\.
The inner loop runs to find the items that need to be moved\.  The inner loop either locates the spot with the smallest value or the spot with the largest value\.   After the inner loop completes, a swap may occur if needed\.   At most, selection sort will make one swap per pass\.  A pass is one complete execution of the inner loop\.

---

## Selection Sort
- pass 0

| 9 | 2 | 8 | 5 | 1 |
| --- | --- | --- | --- | --- |
|  |

- pass 1

| 1 | 2 | 8 | 5 | 9 |
| --- | --- | --- | --- | --- |
|  |

- pass 2

| 1 | 2 | 8 | 5 | 9 |
| --- | --- | --- | --- | --- |
|  |

- pass 3

| 1 | 2 | 5 | 8 | 9 |
| --- | --- | --- | --- | --- |
|  |

- pass 4

| 1 | 2 | 5 | 8 | 9 |
| --- | --- | --- | --- | --- |
|  |

### Speaker notes
Selection sort is pretty effective for small lists, but pretty horrible is used on large lists\.
Selection sort consists of two loops\.
The outer loops run based on the number of items in the list\.
The inner loop runs to find the items that need to be moved\.  The inner loop either locates the spot with the smallest value or the spot with the largest value\.   After the inner loop completes, a swap may occur if needed\.   At most, selection sort will make one swap per pass\.  A pass is one complete execution of the inner loop\.

---

## Insertion with Objects

```
public void selSort\\\(Comparable\\\[\\\] stuff\\\)\\\{
```



```
for\\\(int i=0;i<stuff\\\.length\\\-1;i\\\+\\\+\\\)
```



```
\\\{
```



```
int spot=i;
```



```
for\\\(int j=i;j<stuff\\\.length;j\\\+\\\+\\\)\\\{
```



```
if\\\(stuff\\\[j\\\]\\\.compareTo\\\(stuff\\\[spot\\\]\\\)>0\\\)
```



```
spot=j;
```



```
\\\}
```



```
if\\\(spot==i\\\) continue;
```



```
Comparable save=stuff\\\[i\\\];
```



```
stuff\\\[i\\\]=stuff\\\[spot\\\];
```



```
stuff\\\[spot\\\]=save;
```



```
\\\}
```



```
\\\}
```



- How many swaps per pass?

---

## Selection Sort in Action
- Original List
- Integer\[\] ray = \{90,40,20,30,10,67\};
- pass 1  \-  90  40  20  30  10  67
- pass 2  \-  90  67  20  30  10  40
- pass 3  \-  90  67  40  30  10  20
- pass 4  \-  90  67  40  30  10  20
- pass 5  \-  90  67  40  30  20  10
- pass 6  \-  90  67  40  30  20  10

---

## Insertion Sort

---

## Insertion with primitives

```
void insertionSort\\\( int\\\[\\\] stuff\\\)
```



```
\\\{
```



```
for \\\(int i=1; i< stuff\\\.length; \\\+\\\+i\\\)
```



```
\\\{
```



```
int val = stuff\\\[i\\\];
```



```
int j=i;
```



```
while\\\(j>0&&val<stuff\\\[j\\\-1\\\]\\\)\\\{
```



```
stuff\\\[j\\\]=stuff\\\[j\\\-1\\\];
```



```
j\\\-\\\-;
```



```
\\\}
```



```
stuff\\\[j\\\]=val;
```



```
\\\}
```



```
\\\}
```



- The insertion sort first selects an item and moves items up or down based on the comparison to the selected item\.
- The idea is to get the selected item in proper position by shifting items around in the list\.

---

## Insertion with Objects

```
void insertionSort\\\( Comparable\\\[\\\] stuff\\\)\\\{
```



```
for \\\(int i=1; i< stuff\\\.length; \\\+\\\+i\\\)\\\{
```



```
int bot=0, top=i\\\-1;
```



```
while \\\(bot<=top\\\)\\\{
```



```
int mid=\\\(bot\\\+top\\\)/2;
```



```
if \\\(stuff\\\[mid\\\]\\\.compareTo\\\(stuff\\\[ i \\\]\\\)<0\\\)
```



```
bot=mid\\\+1;
```



```
else top=mid\\\-1;
```



```
\\\}
```



```
Comparable temp= stuff\\\[i\\\];
```



```
for \\\(int j=i; j>bot; \\\-\\\-j\\\)
```



```
stuff\\\[ j\\\]= stuff\\\[ j\\\-1\\\];
```



```
stuff\\\[bot\\\]=temp;
```



```
\\\}
```


---

## Quick Sort  "Divide & Conquer"

```
<svg viewBox="0 0 600 280" style="width: 100%; height: auto; font\\\-family: Arial, sans\\\-serif;"> <g stroke="black" stroke\\\-width="1\\\.5"> <line x1="300" y1="40" x2="150" y2="110" /> <line x1="300" y1="40" x2="450" y2="110" /> <line x1="150" y1="110" x2="75" y2="180" /> <line x1="150" y1="110" x2="225" y2="180" /> <line x1="450" y1="110" x2="375" y2="180" /> <line x1="450" y1="110" x2="525" y2="180" /> <line x1="75" y1="180" x2="37\\\.5" y2="250" /> <line x1="75" y1="180" x2="112\\\.5" y2="250" /> <line x1="225" y1="180" x2="187\\\.5" y2="250" /> <line x1="225" y1="180" x2="262\\\.5" y2="250" /> <line x1="375" y1="180" x2="337\\\.5" y2="250" /> <line x1="375" y1="180" x2="412\\\.5" y2="250" /> <line x1="525" y1="180" x2="487\\\.5" y2="250" /> <line x1="525" y1="180" x2="562\\\.5" y2="250" /> </g> <g text\\\-anchor="middle" dominant\\\-baseline="middle" fill="black" stroke="white" stroke\\\-width="16" paint\\\-order="stroke fill" style="font\\\-weight: normal;"> <text x="300" y="40" style="font\\\-size: 44px;">32</text> <text x="150" y="110" style="font\\\-size: 40px;">16</text> <text x="450" y="110" style="font\\\-size: 40px;">16</text> <text x="75" y="180" style="font\\\-size: 36px;">8</text> <text x="225" y="180" style="font\\\-size: 36px;">8</text> <text x="375" y="180" style="font\\\-size: 36px;">8</text> <text x="525" y="180" style="font\\\-size: 36px;">8</text> <text x="37\\\.5" y="250" style="font\\\-size: 32px;">4</text> <text x="112\\\.5" y="250" style="font\\\-size: 32px;">4</text> <text x="187\\\.5" y="250" style="font\\\-size: 32px;">4</text> <text x="262\\\.5" y="250" style="font\\\-size: 32px;">4</text> <text x="337\\\.5" y="250" style="font\\\-size: 32px;">4</text> <text x="412\\\.5" y="250" style="font\\\-size: 32px;">4</text> <text x="487\\\.5" y="250" style="font\\\-size: 32px;">4</text> <text x="562\\\.5" y="250" style="font\\\-size: 32px;">4</text> </g> </svg>
```



- Quick sort finds a pivot value
- All numbers greater than the pivot move to the right and all numbers less move to the left\.
- This list is then chopped in two and the process above is repeated on the smaller sections\.

---

## Quick Sort
- Quick sort chops up the list into smaller pieces as to avoid processing the whole list at once\.


![](dayone-moment://69F6971914224F92B66B0B2517581864)

---

## 🛝

```
void quickSort\\\(Comparable\\\[\\\] stuff, int low, int high\\\)
```



```
\\\{
```



```
if \\\(low < high\\\)
```



```
\\\{
```



```
int spot = partition\\\(stuff, low, high\\\);
```



```
quickSort\\\(stuff, low, spot\\\);
```



```
quickSort\\\(stuff, spot\\\+1, high\\\);
```



```
\\\}
```



```
\\\}
```



- Arrays\.sort\( \) uses the quickSort
- if sorting primitives\.

---

## 🛝

```
int partition\\\(Comparable\\\[\\\] stuff, int low, int high\\\)
```



```
\\\{
```



```
Comparable pivot = stuff\\\[low\\\];
```



```
int bot = low\\\-1;
```



```
int top = high\\\+1;
```



```
while\\\(bot<top\\\) \\\{
```



```
while \\\(stuff\\\[\\\-\\\-top\\\]\\\.compareTo\\\(pivot\\\) > 0\\\);
```



```
while \\\(stuff\\\[\\\+\\\+bot\\\]\\\.compareTo\\\(pivot\\\) < 0\\\);
```



```
if\\\(bot >= top\\\)
```



```
return top;
```



```
Comparable temp = stuff\\\[bot\\\];
```



```
stuff\\\[bot\\\] = stuff\\\[top\\\];
```



```
stuff\\\[top\\\] = temp;
```



```
\\\}
```



```
\\\}
```


---

## Quick Sort in Action
- Original List:  Integer\[\] ray = \{90,40,20,30,10,67\};
	- pass 1  \-  67  40  20  30  10  90
	- pass 2  \-  10  40  20  30  67  90
	- pass 3  \-  10  40  20  30  67  90
	- pass 4  \-  10  30  20  40  67  90
	- pass 5  \-  10  20  30  40  67  90

---

## Partition:  quickSort
- The quickSort has a N\*Log2N BigO\.
- The quickSort method alone has a Log2N run time, but cannot be run without the partition method\.
- The partition method alone has an N run time and can be run without the quickSort method\.

---

## Merge Sort
- Merge sort splits the list into smaller sections working its way down to groups of two or one\.
- Once the smallest groups are reached, the merge method is called to organize the smaller lists\.
- Merge copies from the sub list to a temp array\.
- The items are put in the temp array in sorted order\.

---

## Merge Sort
- Merge sort chops in half repeatedly to avoid processing the whole list at once\.
1 \. \. 32
1 \. \. 16
17 \. \. 32
1 \. \. 8
1. \. 16
17 \. \.25
26 \. \. 32

---

## Merge with primitives
- Arrays\.sort\( \)  uses mergeSort for objects\.

```
void mergeSort\\\(Comparable\\\[\\\] stuff, int front, int back\\\)
```



```
\\\{
```



```
int mid = \\\(front\\\+back\\\)/2;
```



```
if\\\(mid==front\\\) return;
```



```
mergeSort\\\(stuff, front, mid\\\);
```



```
mergeSort\\\(stuff, mid, back\\\);
```



```
merge\\\(stuff, front, back\\\);
```



```
\\\}
```


---

## Merge with Objects
- Collections\.sort\( \) uses the mergeSort\.

```
void merge\\\(Comparable\\\[\\\] stuff, int front, int back\\\)
```



```
\\\{
```



```
Comparable\\\[\\\] temp = new Comparable\\\[back\\\-front\\\];
```



```
int i = front, j = \\\(front\\\+back\\\)/2, k =0, mid =j;
```



```
while\\\( i<mid && j<back\\\) \\\{
```



```
if\\\(stuff\\\[i\\\]\\\.compareTo\\\(stuff\\\[j\\\]\\\)<0\\\)
```



```
temp\\\[k\\\+\\\+\\\]= stuff\\\[i\\\+\\\+\\\];
```



```
else
```



```
temp\\\[k\\\+\\\+\\\]= stuff\\\[j\\\+\\\+\\\];
```



```
\\\}
```



```
while\\\(i<mid\\\)
```



```
temp\\\[k\\\+\\\+\\\]= stuff\\\[i\\\+\\\+\\\];
```



```
while\\\(j<back\\\)
```



```
temp\\\[k\\\+\\\+\\\]= stuff\\\[j\\\+\\\+\\\];
```



```
for\\\(i = 0; i<back\\\-front; \\\+\\\+i\\\)
```



```
stuff\\\[front\\\+i\\\]=temp\\\[i\\\];
```



```
\\\}
```


---

## Merge Sort in Action
Original List Integer\[\] stuff = \{90,40,20,30,10,67\};
pass 0  \-  90  20  40  30  67  10
pass 1  \-  20  40  90  30  67  10
pass 2  \-  20  40  90  30  10  67
pass 3  \-  20  40  90  10  30  67
pass 4  \-  10  20  30  40  67  90

---

## mergeSort
- The mergeSort has a N\*Log2N BigO\.
- The mergeSort method alone has a Log2N run time, but cannot be run without the merge method\.
- The merge method alone has an N run time and can be run without the mergeSort method\.

---

## 🛝

```
for\\\( int i=0; i<20; i\\\+\\\+\\\)
```



```
System\\\.out\\\.println\\\(i\\\);
```



```
for\\\( int j=0; j<20; j\\\+\\\+\\\)
```



```
for\\\( int k=0; k<20; k\\\+\\\+\\\)
```



```
System\\\.out\\\.println\\\(j\\\*k\\\);
```



- Which section of code would execute the fastest?

---

## 🛝

```
ArrayList<Integer> iRay;
```



```
iRay = new ArrayList<Integer>\\\(\\\);
```



```
for\\\( int i=0; i<20; i\\\+\\\+\\\)
```



```
iRay\\\.add\\\(i\\\);
```



```
ArrayList<Double> dRay;
```



```
dRay = new ArrayList<Double>\\\(\\\);
```



```
for\\\( int j=0; j<20; j\\\+\\\+\\\)
```



```
dRay\\\.add\\\(0,j\\\);
```



- Which section of code would execute the fastest?

---

## General Big O Chart
- Name      Best Case   Avg\. Case   Worst
- Selection Sort     O\(N2\)       O\(N2\)      O\(N2\)
- Bubble Sort    O\(N2\)       O\(N2\)      O\(N2\)
- Insertion Sort     O\(N\) \(@\)    O\(N2\)      O\(N2\)
- @ If the data is sorted, Insertion sort should only make one pass
- through the list\.  If this case is present, Insertion sort would have
- a best case of O\(n\)\.

---

## General Big O Chart
- Name      Best Case   Avg\. Case   Worst
- Merge Sort     O\(N log2 N \)    O\(N log2 N \)   O\(N log2 N \)
- QuickSort  O\(N log2 N \)    O\(N log2 N \)   O\(N2\) \(@\)
- @ QuickSort can degenerate to N2\.   It typically will degenerate on
- sorted data if using a left or right pivot\.   Using a median pivot will
- help tremendously, but QuickSort can still degenerate on certain
- sets of data\.  The split position determines how QuickSort behaves\.

---

<hr/>
/Users/smh/Documents/GitHub/claw8/skills
(none)